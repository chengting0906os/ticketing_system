from datetime import datetime, timezone
from typing import Any, Awaitable, Dict, List, cast

from opentelemetry import trace
import orjson
from redis.asyncio import Redis
from src.service.reservation.driven_adapter.reservation_helper.key_str_generator import (
    make_booking_key,
    make_event_state_key,
    make_seats_bf_key,
    make_sellout_timer_key,
)
from src.service.reservation.driven_adapter.reservation_helper.row_block_manager import (
    row_block_manager,
)
from src.service.reservation.driven_adapter.reservation_helper.seat_finder import (
    seat_finder,
)

from src.platform.database.asyncpg_setting import get_asyncpg_pool
from src.platform.exception.exceptions import DomainError
from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.platform.state.lua_script_executor import lua_script_executor


class AtomicReservationExecutor:
    @staticmethod
    def _extract_subsection_stats(event_state: Dict[str, Any], section_id: str) -> Dict[str, int]:
        """
        Extract subsection statistics from event_state hierarchical structure.

        Args:
            event_state: Full event state dictionary
            section_id: Section ID in format 'A-1' (section-subsection)

        Returns:
            Dict with keys: available, reserved, sold, total

        Example:
            >>> event_state = {
            ...     'sections': {
            ...         'A': {
            ...             'subsections': {
            ...                 '1': {'stats': {'available': 98, 'reserved': 2, 'sold': 0, 'total': 100}}
            ...             }
            ...         }
            ...     }
            ... }
            >>> _extract_subsection_stats(event_state, 'A-1')
            {'available': 98, 'reserved': 2, 'sold': 0, 'total': 100}
        """
        section_name = section_id.split('-')[0]
        subsection_num = section_id.split('-')[1]

        section_stats_data: Dict[str, Any] = (
            event_state.get('sections', {})
            .get(section_name, {})
            .get('subsections', {})
            .get(subsection_num, {})
            .get('stats', {})
        )

        return {
            'available': int(section_stats_data.get('available', 0)),
            'reserved': int(section_stats_data.get('reserved', 0)),
            'sold': int(section_stats_data.get('sold', 0)),
            'total': int(section_stats_data.get('total', 0)),
        }

    @staticmethod
    def _extract_event_stats(event_state: Dict[str, Any]) -> Dict[str, int]:
        """
        Extract event-level statistics from event_state.

        Args:
            event_state: Full event state dictionary

        Returns:
            Dict with keys: available, reserved, sold, total

        Example:
            >>> event_state = {'event_stats': {'available': 498, 'reserved': 2, 'sold': 0, 'total': 500}}
            >>> _extract_event_stats(event_state)
            {'available': 498, 'reserved': 2, 'sold': 0, 'total': 500}
        """
        event_stats_data: Dict[str, Any] = event_state.get('event_stats', {})

        return {
            'available': int(event_stats_data.get('available', 0)),
            'reserved': int(event_stats_data.get('reserved', 0)),
            'sold': int(event_stats_data.get('sold', 0)),
            'total': int(event_stats_data.get('total', 0)),
        }

    async def execute_atomic_reservation(
        self,
        *,
        event_id: int,
        section_id: str,
        booking_id: str,
        bf_key: str,
        seats_to_reserve: List[tuple],
        section_price: int,
    ) -> Dict:
        """
        ## Consistency Guarantees

        1. **Kafka Sequential Processing**: Same booking_id → same partition → sequential processing
        2. **Atomic Commands**: Each HINCRBY/SETBIT executes atomically
        3. **Crash Recovery**: Kafka consumer retries entire operation after crash
        4. **Idempotency**: Application validates and handles duplicate processing

        Args:
            event_id: Event identifier (e.g., 123)
            section_id: Section identifier (e.g., 'A-1')
            booking_id: Booking identifier
            bf_key: Bitfield key for seat states (e.g., 'seats_bf:123:A-1')
            seats_to_reserve: List of (row, seat_num, seat_index, seat_id) tuples
            section_price: Pre-calculated section price (from config). Required.

        Returns:
            Dict with reservation results:
            {
                'success': True,
                'reserved_seats': ['1-1', '1-2'],
                'total_price': 2000,
                'subsection_stats': {'available': 98, 'reserved': 2},
                'event_stats': {'available': 98, 'reserved': 2},
                'event_state': {...},
                'error_message': None
            }
        """
        tracer = trace.get_tracer(__name__)

        with tracer.start_as_current_span(
            'executor.atomic_reservation',
            attributes={
                'booking.id': booking_id,
            },
        ):
            # Get Redis client (lightweight dict lookup)
            client = kvrocks_client.get_client()

            # ========== STEP 0: Read current stats (for sellout tracking) ==========
            event_state_key = make_event_state_key(event_id=event_id)
            result = await client.execute_command('JSON.GET', event_state_key, '$')
            if result:
                event_state_dict: Dict[str, Any] = orjson.loads(result)[0]
                current_stats = event_state_dict.get('event_stats', {})
            else:
                raise DomainError('evenstate cannot be empty')

            current_reserved_count = int(current_stats.get('reserved', 0))
            current_total_seats = int(current_stats.get('total', 0))
            num_seats = len(seats_to_reserve)
            total_price = section_price * num_seats
            reserved_seats = []
            pipe = client.pipeline(
                transaction=True
            )  # Create pipeline with MULTI/EXEC for isolation

            # ========== STEP 1: Reserve seats in bitfield ==========
            # Update each seat's status from AVAILABLE (00) to RESERVED (01)
            for _row, _seat_num, seat_index, seat_id in seats_to_reserve:
                offset = seat_index * 2
                pipe.execute_command('BITFIELD', bf_key, 'SET', 'u2', offset, 1)  # 01 = RESERVED
                reserved_seats.append(seat_id)

            # ========== STEP 2: Update JSON statistics ==========
            event_state_key = make_event_state_key(event_id=event_id)

            pipe.execute_command(
                'JSON.NUMINCRBY', event_state_key, '$.event_stats.available', -num_seats
            )
            pipe.execute_command(
                'JSON.NUMINCRBY', event_state_key, '$.event_stats.reserved', num_seats
            )

            # ========== STEP 3: Fetch updated statistics ==========
            pipe.execute_command('JSON.GET', event_state_key, '$')

            # ========== STEP 4: Save booking metadata ==========
            booking_key = make_booking_key(booking_id=booking_id)
            pipe.hset(
                booking_key,
                mapping={
                    'status': 'RESERVE_SUCCESS',
                    'reserved_seats': orjson.dumps(reserved_seats).decode(),
                    'total_price': str(total_price),
                    'config_key': event_state_key,
                },
            )

            # ========== Execute pipeline (batch all commands) ==========
            results = await pipe.execute()

            # ========== Parse statistics from pipeline results ==========
            # Pipeline order: [BITFIELD×num_seats, JSON.NUMINCRBY×2, JSON.GET, HSET]
            event_state_idx = (
                num_seats + 2
            )  # Skip BITFIELD results + 2 JSON.NUMINCRBY (event-level only)
            json_state_result = results[event_state_idx]
            event_state: Dict[str, Any] = orjson.loads(json_state_result)[0]
            subsection_stats = self._extract_subsection_stats(event_state, section_id)
            event_stats = self._extract_event_stats(event_state)

            # ========== STEP 4.5: Update row_blocks for Python seat finder ==========
            # Extract cols from event_state (already fetched in STEP 0)
            section_name, subsection_num = section_id.split('-')
            cols = (
                event_state_dict.get('sections', {})
                .get(section_name, {})
                .get('subsections', {})
                .get(subsection_num, {})
                .get('cols', 0)
            )
            if cols > 0:
                # Group reserved seats by row: {row: [seat_index_in_row, ...]}
                seats_by_row: Dict[int, List[int]] = {}
                for row, seat_num, _seat_index, _seat_id in seats_to_reserve:
                    seat_index_in_row = seat_num - 1  # Convert to 0-indexed
                    if row not in seats_by_row:
                        seats_by_row[row] = []
                    seats_by_row[row].append(seat_index_in_row)

                # Update row_blocks for each affected row
                for row, seat_indices in seats_by_row.items():
                    try:
                        await row_block_manager.remove_seats_from_blocks(
                            event_id=event_id,
                            section=section_name,
                            subsection=int(subsection_num),
                            row=row,
                            seat_indices=seat_indices,
                            cols=cols,
                        )
                    except Exception as e:
                        Logger.base.warning(f'[ROW-BLOCKS] Failed to update blocks: {e}')

            # ========== STEP 5: Track sellout timing (AFTER pipeline) ==========
            try:
                await self._track_first_ticket(
                    client=client,
                    event_id=event_id,
                    current_reserved_count=current_reserved_count,
                )
            except Exception as e:
                Logger.base.warning(
                    f'[SELLOUT-TRACKING] Failed to track first ticket reservation | '
                    f'event_id={event_id} | '
                    f'current_reserved_count={current_reserved_count} | '
                    f'error_type={type(e).__name__} | '
                    f'error={str(e)}',
                    exc_info=True,
                )

            try:
                await self._track_all_reserved(
                    client=client,
                    event_id=event_id,
                    new_available_count=event_stats.get('available', 0),
                    total_seats=current_total_seats,
                )
            except Exception as e:
                Logger.base.warning(
                    f'[SELLOUT-TRACKING] Failed to track full reservation | '
                    f'event_id={event_id} | '
                    f'new_available_count={event_stats.get("available", 0)} | '
                    f'total_seats={current_total_seats} | '
                    f'error_type={type(e).__name__} | '
                    f'error={str(e)}',
                    exc_info=True,
                )

            # Return complete reservation result
            return {
                'success': True,
                'reserved_seats': reserved_seats,
                'total_price': total_price,
                'subsection_stats': subsection_stats,
                'event_stats': event_stats,
                'event_state': event_state,
                'error_message': None,
            }

    async def execute_find_and_reserve(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        booking_id: str,
        quantity: int,
        # Config from upstream (avoids redundant Kvrocks lookups in Lua scripts)
        rows: int,
        cols: int,
        price: int,
    ) -> Dict:
        """
        Find and reserve seats in one method (best_available mode).

        Config (rows, cols, price) is passed from upstream through the event chain,
        avoiding redundant Kvrocks lookups in Lua script.

        If config is 0 (cache miss upstream), fetches from Kvrocks here.

        Combines find_consecutive_seats (Lua) + execute_atomic_reservation (Pipeline).
        """
        tracer = trace.get_tracer(__name__)
        section_id = f'{section}-{subsection}'
        bf_key = make_seats_bf_key(event_id=event_id, section_id=section_id)

        with tracer.start_as_current_span(
            'executor.find_and_reserve',
            attributes={
                'booking.id': booking_id,
            },
        ):
            # ========== STEP 0: Fetch config if missing (cache miss upstream) ==========
            # Query PostgreSQL to distribute load (instead of Kvrocks)
            if rows == 0 or cols == 0:
                pool = await get_asyncpg_pool()
                async with pool.acquire() as conn:
                    row_result = await conn.fetchrow(
                        'SELECT seating_config FROM event WHERE id = $1', event_id
                    )
                    if row_result:
                        seating_config = row_result['seating_config']
                        # Find section and subsection in seating_config
                        for sec in seating_config.get('sections', []):
                            if sec.get('name') == section:
                                price = sec.get('price', 0)
                                for subsec in sec.get('subsections', []):
                                    if subsec.get('id') == subsection:
                                        rows = subsec.get('rows', 0)
                                        cols = subsec.get('cols', 0)
                                        break
                                break

            # ========== STEP 1: Find consecutive seats ==========
            # Uses A/B strategy switch (SEAT_FINDER_STRATEGY env var)
            found_seats = await seat_finder.find_consecutive_seats(
                bf_key=bf_key,
                rows=rows,
                cols=cols,
                quantity=quantity,
                # For Python strategy
                event_id=event_id,
                section=section,
                subsection=subsection,
            )

            if found_seats is None:
                return {
                    'success': False,
                    'reserved_seats': [],
                    'total_price': 0,
                    'subsection_stats': {},
                    'event_stats': {},
                    'event_state': {},
                    'error_message': f'No {quantity} consecutive seats available',
                }

            # ========== STEP 2: Convert to reservation format ==========
            # found_seats: List[(row, seat_num, seat_index)]
            seats_to_reserve = [
                (row, seat_num, seat_index, f'{row}-{seat_num}')
                for row, seat_num, seat_index in found_seats
            ]

            # ========== STEP 3: Execute atomic reservation ==========
            return await self.execute_atomic_reservation(
                event_id=event_id,
                section_id=section_id,
                booking_id=booking_id,
                bf_key=bf_key,
                seats_to_reserve=seats_to_reserve,
                section_price=price,
            )

    async def execute_manual_reservation(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        booking_id: str,
        seat_ids: List[str],
    ) -> Dict:
        """
        Verify and reserve manually selected seats (manual mode).

        Lua script fetches config, validates seats, returns verified data.
        Then execute_atomic_reservation does the actual reservation.
        """
        tracer = trace.get_tracer(__name__)
        section_id = f'{section}-{subsection}'
        bf_key = make_seats_bf_key(event_id=event_id, section_id=section_id)

        with tracer.start_as_current_span(
            'executor.manual_reservation',
            attributes={
                'booking.id': booking_id,
            },
        ):
            client = kvrocks_client.get_client()
            event_state_key = make_event_state_key(event_id=event_id)

            # ========== STEP 1: Verify seats via Lua (fetches config + validates) ==========
            try:
                lua_result = await lua_script_executor.verify_manual_seats(
                    client=client,
                    keys=[bf_key, event_state_key],
                    args=[str(event_id), section, str(subsection)] + seat_ids,
                )
            except Exception as e:
                error_msg = str(e)
                # Parse Lua error format: "SEAT_UNAVAILABLE: Seat A-1-1-5 is already RESERVED"
                if ':' in error_msg:
                    error_msg = error_msg.split(':', 1)[1].strip()
                return {
                    'success': False,
                    'reserved_seats': [],
                    'total_price': 0,
                    'subsection_stats': {},
                    'event_stats': {},
                    'event_state': {},
                    'error_message': error_msg,
                }

            if lua_result is None:
                return {
                    'success': False,
                    'reserved_seats': [],
                    'total_price': 0,
                    'subsection_stats': {},
                    'event_stats': {},
                    'event_state': {},
                    'error_message': 'Lua verification returned no data',
                }

            # Parse Lua result: {"seats": [[row, seat_num, seat_index, seat_id], ...], "cols": 20, "price": 1800}
            lua_data = orjson.loads(lua_result)
            verified_seats = lua_data['seats']
            section_price = lua_data['price']

            # ========== STEP 2: Convert to reservation format ==========
            seats_to_reserve = [
                (row, seat_num, seat_index, seat_id)
                for row, seat_num, seat_index, seat_id in verified_seats
            ]

            # ========== STEP 3: Execute atomic reservation ==========
            return await self.execute_atomic_reservation(
                event_id=event_id,
                section_id=section_id,
                booking_id=booking_id,
                bf_key=bf_key,
                seats_to_reserve=seats_to_reserve,
                section_price=section_price,
            )

    @staticmethod
    async def _track_first_ticket(
        *,
        client: Redis,
        event_id: int,
        current_reserved_count: int,
    ) -> None:
        # Only track when this is the first ticket (reserved was 0 before)
        if current_reserved_count != 0:
            return

        timer_key = make_sellout_timer_key(event_id=event_id)
        now = datetime.now(timezone.utc).isoformat()

        # Simple HSET - Kafka partition ordering guarantees this is the first reservation
        await cast(Awaitable[int], client.hset(timer_key, 'first_ticket_reserved_at', now))

        Logger.base.info(
            f'📊 [SELLOUT-TRACKING] First ticket reserved for event_id={event_id} at {now}'
        )

    @staticmethod
    async def _track_all_reserved(
        *,
        client: Redis,
        event_id: int,
        new_available_count: int,
        total_seats: int,
    ) -> None:
        # Only track when just sold out (available became 0)
        if new_available_count != 0:
            return

        timer_key = make_sellout_timer_key(event_id=event_id)

        # Fetch first ticket reserved timestamp
        first_ticket_reserved_at_raw = await cast(
            Awaitable[str], client.hget(timer_key, 'first_ticket_reserved_at')
        )

        if not first_ticket_reserved_at_raw:
            # No first ticket recorded, skip tracking
            return

        # Decode bytes to string
        first_ticket_reserved_at_str = (
            first_ticket_reserved_at_raw.decode()
            if isinstance(first_ticket_reserved_at_raw, bytes)
            else first_ticket_reserved_at_raw
        )

        # Parse timestamps and calculate duration
        first_ticket_reserved_at = datetime.fromisoformat(first_ticket_reserved_at_str)
        sold_out_at = datetime.now(timezone.utc)
        duration = (sold_out_at - first_ticket_reserved_at).total_seconds()

        # Save sellout stats to Kvrocks
        await cast(
            Awaitable[int],
            client.hset(
                timer_key,
                mapping={
                    'fully_reserved_at': sold_out_at.isoformat(),
                    'duration_seconds': str(duration),
                },
            ),
        )

        Logger.base.info(
            f'🎉 [SELLOUT-TRACKING] Event {event_id} SOLD OUT! Duration: {duration:.2f}s '
            f'({duration / 60:.2f} min), Total seats: {total_seats}'
        )
