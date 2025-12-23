"""
Atomic Reservation Executor

Handles atomic seat reservation with idempotency control via booking metadata.
"""

from typing import Any, Dict, List

from opentelemetry import trace
import orjson

from src.platform.database.asyncpg_setting import get_asyncpg_pool
from src.platform.exception.exceptions import DomainError
from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.platform.state.lua_script_executor import lua_script_executor
from src.service.reservation.driven_adapter.state.reservation_helper.key_str_generator import (
    make_booking_key,
    make_event_state_key,
    make_seats_bf_key,
)
from src.service.shared_kernel.app.interface.i_booking_metadata_handler import (
    IBookingMetadataHandler,
)


class AtomicReservationExecutor:
    """
    Atomic Reservation Executor - Kvrocks seat reservation with idempotency

    Flow:
    1. Check booking metadata status (idempotency)
    2. If already RESERVE_SUCCESS, return cached result (no-op)
    3. If not, find/verify seats and reserve in Kvrocks (atomic via pipeline)
    4. Update booking metadata to RESERVE_SUCCESS

    Status Flow (Kvrocks metadata):
    - PENDING_RESERVATION → RESERVE_SUCCESS (after successful reservation)
    - PENDING_RESERVATION → RESERVE_FAILED (if reservation fails)

    Note: Uses MULTI/EXEC pipeline for atomicity
    """

    def __init__(self, *, booking_metadata_handler: IBookingMetadataHandler) -> None:
        self.booking_metadata_handler = booking_metadata_handler
        self.tracer = trace.get_tracer(__name__)

    @staticmethod
    def _error_result(error_message: str) -> Dict:
        """Create error result"""
        return {
            'success': False,
            'reserved_seats': [],
            'total_price': 0,
            'subsection_stats': {},
            'event_stats': {},
            'error_message': error_message,
        }

    async def check_reservation_status(self, *, booking_id: str) -> Dict | None:
        """
        Check booking status for reservation idempotency.

        Returns:
            - None: Not yet reserved (PENDING_RESERVATION or no metadata), proceed with reservation
            - Dict with success=True: Already RESERVE_SUCCESS, return cached result
            - Dict with success=False: Already RESERVE_FAILED, return error
        """
        metadata = await self.booking_metadata_handler.get_booking_metadata(booking_id=booking_id)

        if not metadata:
            # No metadata found - this shouldn't happen in normal flow
            # (Ticketing Service should create it first)
            Logger.base.warning(
                f'⚠️ [IDEMPOTENCY] No metadata found for booking {booking_id}, proceeding anyway'
            )
            return None

        status = metadata.get('status')

        if status == 'RESERVE_SUCCESS':
            # Already successfully reserved
            Logger.base.info(
                f'✅ [IDEMPOTENCY] Booking {booking_id} already RESERVE_SUCCESS - returning cached result'
            )

            reserved_seats = orjson.loads(metadata.get('reserved_seats', '[]'))
            total_price = int(metadata.get('total_price', 0))
            subsection_stats = orjson.loads(metadata.get('subsection_stats', '{}'))
            event_stats = orjson.loads(metadata.get('event_stats', '{}'))

            return {
                'success': True,
                'reserved_seats': reserved_seats,
                'total_price': total_price,
                'subsection_stats': subsection_stats,
                'event_stats': event_stats,
                'error_message': None,
            }

        elif status == 'RESERVE_FAILED':
            # Already failed
            error_msg = metadata.get('error_message', 'Reservation previously failed')
            Logger.base.warning(
                f'⚠️ [IDEMPOTENCY] Booking {booking_id} already RESERVE_FAILED: {error_msg}'
            )
            return self._error_result(error_msg)

        elif status == 'PENDING_RESERVATION':
            # Initial state - proceed with reservation
            return None

        else:
            # Unknown status - log warning but proceed anyway
            Logger.base.warning(
                f'⚠️ [IDEMPOTENCY] Unknown status {status} for booking {booking_id}, proceeding'
            )
            return None

    async def _save_reservation_failure(self, *, booking_id: str, error_message: str) -> None:
        """Save failed reservation to metadata"""
        await self.booking_metadata_handler.update_booking_status(
            booking_id=booking_id, status='RESERVE_FAILED', error_message=error_message
        )
        Logger.base.warning(f'❌ [STATUS] Updated booking {booking_id} to RESERVE_FAILED')

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
            # Update each seat's status from AVAILABLE (0) to RESERVED (1)
            for _row, _seat_num, seat_index, seat_id in seats_to_reserve:
                pipe.execute_command('BITFIELD', bf_key, 'SET', 'u1', seat_index, 1)  # 1 = RESERVED
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
            # ========== STEP 0: Idempotency check ==========
            existing = await self.check_reservation_status(booking_id=booking_id)
            if existing:
                return existing

            client = kvrocks_client.get_client()

            # ========== STEP 2: Fetch config if missing (cache miss upstream) ==========
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

            # ========== STEP 3: Find consecutive seats ==========
            # Config passed via ARGV (avoids Kvrocks fetch in Lua)
            lua_result = await lua_script_executor.find_consecutive_seats(
                client=client,
                keys=[bf_key],
                args=[str(rows), str(cols), str(quantity)],
            )

            if lua_result is None:
                error_msg = f'No {quantity} consecutive seats available'
                await self._save_reservation_failure(booking_id=booking_id, error_message=error_msg)
                return self._error_result(error_msg)

            # Parse Lua result: {"seats": [[row, seat_num, seat_index], ...], "rows": 25, "cols": 20, "price": 0}
            lua_data = orjson.loads(lua_result)
            found_seats = lua_data['seats']

            # ========== STEP 4: Convert to reservation format ==========
            seats_to_reserve = [
                (row, seat_num, seat_index, f'{row}-{seat_num}')
                for row, seat_num, seat_index in found_seats
            ]

            # ========== STEP 5: Execute atomic reservation ==========
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
            # ========== STEP 0: Idempotency check ==========
            existing = await self.check_reservation_status(booking_id=booking_id)
            if existing:
                return existing

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
                # Parse Lua error format: "SEAT_UNAVAILABLE: Seat 1-5 is already RESERVED"
                if ':' in error_msg:
                    error_msg = error_msg.split(':', 1)[1].strip()
                await self._save_reservation_failure(booking_id=booking_id, error_message=error_msg)
                return self._error_result(error_msg)

            if lua_result is None:
                error_msg = 'Lua verification returned no data'
                await self._save_reservation_failure(booking_id=booking_id, error_message=error_msg)
                return self._error_result(error_msg)

            # Parse Lua result: {"seats": [[row, seat_num, seat_index, seat_id], ...], "cols": 20}
            lua_data = orjson.loads(lua_result)
            verified_seats = lua_data['seats']

            # Fetch section price from event_state
            price_path = f'$.sections.{section}.price'
            price_result = await client.execute_command('JSON.GET', event_state_key, price_path)
            section_price = orjson.loads(price_result)[0] if price_result else 0

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

    # ========== Split Methods for New 5-Step Flow ==========

    async def execute_find_seats(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        quantity: int,
        rows: int,
        cols: int,
        price: int,
    ) -> Dict:
        """
        Find available seats via Lua script (Step 2 - BEST_AVAILABLE mode).

        Lua script only, no Pipeline update.
        Returns seats to reserve for downstream PostgreSQL + Pipeline steps.
        """
        section_id = f'{section}-{subsection}'
        bf_key = make_seats_bf_key(event_id=event_id, section_id=section_id)
        client = kvrocks_client.get_client()

        # Execute Lua script to find consecutive seats
        lua_result = await lua_script_executor.find_consecutive_seats(
            client=client,
            keys=[bf_key],
            args=[str(rows), str(cols), str(quantity)],
        )

        if lua_result is None:
            return {
                'success': False,
                'seats_to_reserve': [],
                'total_price': 0,
                'error_message': f'No {quantity} consecutive seats available',
            }

        # Parse Lua result: {"seats": [[row, seat_num, seat_index], ...]}
        lua_data = orjson.loads(lua_result)
        found_seats = lua_data['seats']

        # Convert to reservation format: [(row, seat_num, seat_index, seat_id), ...]
        seats_to_reserve = [
            (row, seat_num, seat_index, f'{row}-{seat_num}')
            for row, seat_num, seat_index in found_seats
        ]

        return {
            'success': True,
            'seats_to_reserve': seats_to_reserve,
            'total_price': price * len(seats_to_reserve),
            'error_message': None,
        }

    async def execute_verify_seats(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        seat_ids: List[str],
        price: int,
    ) -> Dict:
        """
        Verify specified seats are available via Lua script (Step 2 - MANUAL mode).

        Lua script only, no Pipeline update.
        Returns verified seats for downstream PostgreSQL + Pipeline steps.
        """
        section_id = f'{section}-{subsection}'
        bf_key = make_seats_bf_key(event_id=event_id, section_id=section_id)
        event_state_key = make_event_state_key(event_id=event_id)
        client = kvrocks_client.get_client()

        try:
            lua_result = await lua_script_executor.verify_manual_seats(
                client=client,
                keys=[bf_key, event_state_key],
                args=[str(event_id), section, str(subsection)] + seat_ids,
            )
        except Exception as e:
            error_msg = str(e)
            # Parse Lua error format: "SEAT_UNAVAILABLE: Seat 1-5 is already RESERVED"
            if ':' in error_msg:
                error_msg = error_msg.split(':', 1)[1].strip()
            return {
                'success': False,
                'seats_to_reserve': [],
                'total_price': 0,
                'error_message': error_msg,
            }

        if lua_result is None:
            return {
                'success': False,
                'seats_to_reserve': [],
                'total_price': 0,
                'error_message': 'Lua verification returned no data',
            }

        # Parse Lua result: {"seats": [[row, seat_num, seat_index, seat_id], ...], "cols": 20}
        lua_data = orjson.loads(lua_result)
        verified_seats = lua_data['seats']

        # Convert to reservation format
        seats_to_reserve = [
            (row, seat_num, seat_index, seat_id)
            for row, seat_num, seat_index, seat_id in verified_seats
        ]

        return {
            'success': True,
            'seats_to_reserve': seats_to_reserve,
            'total_price': price * len(seats_to_reserve),
            'error_message': None,
        }

    async def execute_update_seat_map(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        seats_to_reserve: List[tuple],
        total_price: int,
    ) -> Dict:
        """
        Update seat map in Kvrocks via Pipeline (Step 4 of new flow).

        Pipeline only, no Lua script.
        Executes atomic updates: BITFIELD SET for each seat.
        """
        section_id = f'{section}-{subsection}'
        bf_key = make_seats_bf_key(event_id=event_id, section_id=section_id)
        client = kvrocks_client.get_client()

        reserved_seats = []
        pipe = client.pipeline(transaction=True)

        for _row, _seat_num, seat_index, seat_id in seats_to_reserve:
            pipe.execute_command('BITFIELD', bf_key, 'SET', 'u1', seat_index, 1)
            reserved_seats.append(seat_id)

        await pipe.execute()

        return {
            'success': True,
            'reserved_seats': reserved_seats,
            'total_price': total_price,
            'error_message': None,
        }
