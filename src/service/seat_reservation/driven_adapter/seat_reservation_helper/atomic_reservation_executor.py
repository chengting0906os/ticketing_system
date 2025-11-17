from datetime import datetime, timezone
import os
from typing import Any, Awaitable, Dict, List, cast

from opentelemetry import trace
import orjson
from redis.asyncio import Redis

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client


# Get key prefix from environment for test isolation
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')


def _make_key(key: str) -> str:
    """Add prefix to key for test isolation in parallel testing"""
    return f'{_KEY_PREFIX}{key}'


class AtomicReservationExecutor:
    async def fetch_total_price(
        self,
        *,
        event_id: int,
        section_id: str,
        seats_to_reserve: List[tuple],
    ) -> int:
        """
        Pre-fetch section price from event config JSON and calculate total.

        ## Why Pre-fetch?

        Prices are stored in unified event config JSON (event_state:{event_id}).
        Each section has ONE price (not per seat), simplifying the data structure.

        We pre-fetch the config once, which is safe because:
        - Seat prices are READ-ONLY during reservation (they don't change)
        - This doesn't affect consistency (we still verify availability later)

        ## Data Structure

        event_state:{event_id} contains:
        {
            "sections": {
                "A-1": {"rows": 25, "seats_per_row": 20, "price": 1000},
                "B-1": {"rows": 20, "seats_per_row": 15, "price": 2000}
            }
        }

        ## Example

        Input: seats_to_reserve = [(1, 1, 0, 'A-1-1-1'), (1, 2, 1, 'A-1-1-2')]
        Output: 2000

        Args:
            event_id: Event identifier (e.g., 123)
            section_id: Section identifier (e.g., 'A-1')
            seats_to_reserve: List of (row, seat_num, seat_index, seat_id) tuples
                Example: [(1, 1, 0, 'A-1-1-1'), (1, 2, 1, 'A-1-1-2')]

        Returns:
            total_price: Sum of all prices (e.g., 2000)
        """
        tracer = trace.get_tracer(__name__)

        with tracer.start_as_current_span(
            'executor.fetch_price',
            attributes={
                'event.id': event_id,
                'seat.section_id': section_id,
                'seat.count': len(seats_to_reserve),
            },
        ):
            # Get Redis client (lightweight dict lookup, returns existing connection pool)
            client = kvrocks_client.get_client()
            config_key = _make_key(f'event_state:{event_id}')

            # Fetch event config JSON
            try:
                # JSON.GET with $ returns: '[{"event_stats":{...},"sections":{...}}]'
                result = await client.execute_command('JSON.GET', config_key, '$')

                if not result:
                    Logger.base.error(
                        f'❌ [EXECUTOR-READ] No event config found for event_id={event_id}'
                    )
                    event_state = {}
                else:
                    # Parse JSON string array and extract first element
                    event_state_list = orjson.loads(result)
                    event_state = event_state_list[0]

            except Exception as e:
                Logger.base.error(f'❌ [EXECUTOR-READ] Failed to fetch event config: {e}')
                event_state = {}

            # Extract section price from hierarchical structure
            # section_id format: "A-1" -> extract section name "A" for price lookup
            section_name = section_id.split('-')[0]  # e.g., "A-1" -> "A"
            section_config = event_state.get('sections', {}).get(section_name, {})
            section_price = section_config.get('price', 0)

            if not section_config:
                Logger.base.error(
                    f'❌ [EXECUTOR-READ] Section not found! Available sections: {list(event_state.get("sections", {}).keys())}, '
                    f'Requested: {section_name} (from {section_id})'
                )

            # Calculate total price
            # All seats in same section have same price
            num_seats = len(seats_to_reserve)
            total_price = section_price * num_seats

            Logger.base.debug(
                f'💰 [PRICE-FETCH] Section {section_id}: {num_seats} seats × {section_price} = {total_price}'
            )

            return total_price

    async def execute_atomic_reservation(
        self,
        *,
        event_id: int,
        section_id: str,
        booking_id: str,
        bf_key: str,
        seats_to_reserve: List[tuple],
        total_price: int,
    ) -> Dict:
        """
        Execute seat reservation using Redis pipeline for batching.

        ## Atomicity Strategy

        Each Redis command is inherently atomic:
        - SETBIT: Atomically sets bits for seat status
        - HINCRBY: Atomically increments counters (no read-modify-write race)
        - HSET: Atomically sets hash fields

        Pipeline is used for performance (reducing network round-trips), not transactions.

        ## Consistency Guarantees

        1. **Kafka Sequential Processing**: Same booking_id → same partition → sequential processing
        2. **Atomic Commands**: Each HINCRBY/SETBIT executes atomically
        3. **Crash Recovery**: Kafka consumer retries entire operation after crash
        4. **Idempotency**: Application validates and handles duplicate processing

        **Why Simple Pipeline is Sufficient**:
        - ✅ No concurrent access (Kafka partitioning)
        - ✅ Each command atomic (Redis guarantees)
        - ✅ Crash recovery via Kafka retry

        ## Pipeline Result Parsing

        The pipeline returns a list of results in order:
        ```
        [
            # For each seat: 2 setbit results (bit0, bit1)
            1, 1,  # Seat 1: setbit results
            1, 1,  # Seat 2: setbit results
            ...

            # Statistics updates: 4 hincrby results
            99, 1, 99, 1,  # (section_available, section_reserved, event_available, event_reserved)

            # Statistics fetch: 2 hgetall results
            {b'available': b'99', b'reserved': b'1'},  # section_stats
            {b'available': b'99', b'reserved': b'1'},  # event_stats

            # Booking metadata save: 1 hset result
            4  # Number of fields set
        ]
        ```

        To find stats in results:
        - subsection_stats_idx = (num_seats * 2) + 4
        - event_stats_idx = subsection_stats_idx + 1

        ## Example

        For 2 seats:
        - Results[0-3]: 4 setbit results (2 seats × 2 bits)
        - Results[4-7]: 4 hincrby results
        - Results[8]: subsection_stats ← (2*2 + 4 = 8)
        - Results[9]: event_stats ← (8 + 1 = 9)
        - Results[10]: hset result

        Args:
            event_id: Event identifier (e.g., 123)
            section_id: Section identifier (e.g., 'A-1')
            booking_id: Booking identifier (e.g., '01234567-89ab-cdef-0123-456789abcdef')
            bf_key: Bitfield key for seat states (e.g., 'seats_bf:123:A-1')
            seats_to_reserve: List of (row, seat_num, seat_index, seat_id) tuples
                Example: [(1, 1, 0, 'A-1-1-1'), (1, 2, 1, 'A-1-1-2')]
            total_price: Pre-calculated total price (e.g., 2000)

        Returns:
            Dict with reservation results:
            {
                'success': True,
                'reserved_seats': ['A-1-1-1', 'A-1-1-2'],
                'total_price': 2000,
                'subsection_stats': {'available': 98, 'reserved': 2},
                'event_stats': {'available': 98, 'reserved': 2},
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

            # ========== STEP 0: Read current stats BEFORE pipeline (for sellout tracking) ==========
            # We need to know the current reserved count to determine if this is the first ticket
            event_state_key = _make_key(f'event_state:{event_id}')

            # Read entire event_state (simpler and more reliable than JSONPath $.event_stats)
            # JSONPath $ returns bytes like b'[{"event_stats": {...}}]'
            result = await client.execute_command('JSON.GET', event_state_key, '$')
            if not result:
                # If JSON key doesn't exist, initialize with empty stats
                current_stats = {}
            else:
                # Parse bytes to list, then unwrap to get dict
                event_state_dict: Dict[str, Any] = orjson.loads(result)[0]
                current_stats = event_state_dict.get('event_stats', {})

            current_reserved_count = int(current_stats.get('reserved', 0))
            current_total_seats = int(current_stats.get('total', 0))

            # Create pipeline with MULTI/EXEC for isolation
            # transaction=True: Prevents command interleaving by other clients
            pipe = client.pipeline(transaction=True)
            reserved_seats = []

            # ========== STEP 1: Reserve seats in bitfield ==========
            # Update each seat's status from AVAILABLE (00) to RESERVED (01)
            #
            # Bitfield encoding (2 bits per seat):
            # - AVAILABLE: 00 (bit0=0, bit1=0)
            # - RESERVED:  01 (bit0=0, bit1=1)
            # - SOLD:      10 (bit0=1, bit1=0)
            #
            # Example: Seat at index 5
            # - offset = 5 * 2 = 10
            # - bit0 at position 10 → set to 0
            # - bit1 at position 11 → set to 1
            for _row, _seat_num, seat_index, seat_id in seats_to_reserve:
                offset = seat_index * 2
                pipe.setbit(bf_key, offset, 0)  # bit0 = 0
                pipe.setbit(bf_key, offset + 1, 1)  # bit1 = 1
                reserved_seats.append(seat_id)

            # ========== STEP 2: Update statistics ==========
            # Update both subsection and event-level statistics atomically in single JSON
            # After reserving 2 seats:
            # - event_state:123.sections.A.subsections.1.stats → {available: 98, reserved: 2}
            # - event_state:123.event_stats → {available: 498, reserved: 2}
            config_key = _make_key(f'event_state:{event_id}')
            num_seats = len(seats_to_reserve)

            # Extract section and subsection for hierarchical navigation
            section_name = section_id.split('-')[0]  # e.g., "A-1" -> "A"
            subsection_num = section_id.split('-')[1]  # e.g., "A-1" -> "1"

            # ✨ Update subsection stats in JSON (atomic JSON.NUMINCRBY with hierarchical path)
            pipe.execute_command(
                'JSON.NUMINCRBY',
                config_key,
                f"$.sections['{section_name}'].subsections['{subsection_num}'].stats.available",
                -num_seats,
            )
            pipe.execute_command(
                'JSON.NUMINCRBY',
                config_key,
                f"$.sections['{section_name}'].subsections['{subsection_num}'].stats.reserved",
                num_seats,
            )

            # ✨ NEW: Update event-level stats in JSON (no separate Hash)
            pipe.execute_command(
                'JSON.NUMINCRBY', config_key, '$.event_stats.available', -num_seats
            )
            pipe.execute_command('JSON.NUMINCRBY', config_key, '$.event_stats.reserved', num_seats)

            # ========== STEP 3: Fetch updated statistics ==========
            # ✨ Get ENTIRE event_state JSON (all sections + event_stats) for Kafka event
            # This eliminates lazy loading in ticketing service - cache always fully populated
            pipe.execute_command('JSON.GET', config_key, '$')

            # ========== STEP 4: Save booking metadata ==========
            # Save booking metadata for tracking reservation status
            # Note: We save stats references (keys) here, not the actual stats
            # The actual stats will be decoded from the pipeline results
            booking_key = _make_key(f'booking:{booking_id}')
            pipe.hset(
                booking_key,
                mapping={
                    'status': 'RESERVE_SUCCESS',
                    'reserved_seats': orjson.dumps(reserved_seats).decode(),
                    'total_price': str(total_price),
                    'config_key': config_key,  # ✨ Unified config (sections + event_stats)
                },
            )

            # ========== Execute pipeline (batch all commands) ==========
            # Execute all queued commands in sequence
            # Each individual command (SETBIT, JSON.NUMINCRBY, JSON.GET, HSET) is atomic
            # Pipeline reduces network round-trips for better performance
            results = await pipe.execute()

            # ========== Parse statistics from pipeline results ==========
            # Calculate indices based on pipeline structure:
            #
            # Results layout:
            # - [0 to num_seats*2-1]: setbit results (2 per seat)
            # - [num_seats*2]: JSON.NUMINCRBY section available (returns new value as string "98")
            # - [num_seats*2+1]: JSON.NUMINCRBY section reserved (returns new value as string "2")
            # - [num_seats*2+2]: JSON.NUMINCRBY event available (returns new value as string "498")
            # - [num_seats*2+3]: JSON.NUMINCRBY event reserved (returns new value as string "2")
            # - [num_seats*2+4]: JSON.GET event_state (ENTIRE config with ALL sections + event_stats)
            # - [num_seats*2+5]: HSET result (booking metadata)
            #
            # Example with 2 seats:
            # - Results[0-3]: 4 setbit results
            # - Results[4-7]: 4 JSON.NUMINCRBY results (section x2 + event x2)
            # - Results[8]: event_state (JSON.GET $) ← (2*2 + 4)
            # - Results[9]: HSET result
            event_state_idx = num_seats * 2 + 4

            # Parse JSON.GET result from pipeline (format: bytes from Kvrocks)
            # JSONPath $ returns bytes like b'[{"event_stats": {...}}]'
            json_config_result = results[event_state_idx]
            event_state: Dict[str, Any] = (
                orjson.loads(json_config_result)[0] if json_config_result else {}
            )

            # Extract specific subsection stats from hierarchical structure
            section_name = section_id.split('-')[0]  # e.g., "A-1" -> "A"
            subsection_num = section_id.split('-')[1]  # e.g., "A-1" -> "1"
            section_stats_data: Dict[str, Any] = (
                event_state.get('sections', {})
                .get(section_name, {})
                .get('subsections', {})
                .get(subsection_num, {})
                .get('stats', {})
            )
            subsection_stats = {
                'available': int(section_stats_data.get('available', 0)),
                'reserved': int(section_stats_data.get('reserved', 0)),
                'sold': int(section_stats_data.get('sold', 0)),
                'total': int(section_stats_data.get('total', 0)),
            }

            event_stats_data: Dict[str, Any] = event_state.get('event_stats', {})
            event_stats = {
                'available': int(event_stats_data.get('available', 0)),
                'reserved': int(event_stats_data.get('reserved', 0)),
                'sold': int(event_stats_data.get('sold', 0)),
                'total': int(event_stats_data.get('total', 0)),
            }

            # ========== STEP 5: Track sellout timing (AFTER pipeline) ==========
            # Track first ticket sold (if this was the first reservation)
            # Wrapped in try-except to ensure sellout tracking doesn't break reservation flow
            try:
                await self._track_first_ticket(
                    client=client,
                    event_id=event_id,
                    current_reserved_count=current_reserved_count,
                )
            except Exception:
                # Silently fail if sellout tracking fails (non-critical feature)
                pass

            # Track sold out event (if event just sold out)
            try:
                await self._track_all_reserved(
                    client=client,
                    event_id=event_id,
                    new_available_count=event_stats.get('available', 0),
                    total_seats=current_total_seats,
                )
            except Exception:
                # Silently fail if sellout tracking fails (non-critical feature)
                pass

            # Return complete reservation result (includes event_state for use case to broadcast)
            return {
                'success': True,
                'reserved_seats': reserved_seats,
                'total_price': total_price,
                'subsection_stats': subsection_stats,  # For SSE broadcasting
                'event_stats': event_stats,  # For SSE broadcasting
                'event_state': event_state,  # For Redis Pub/Sub broadcasting (use case responsibility)
                'error_message': None,
            }

    @staticmethod
    @Logger.io
    async def _track_first_ticket(
        *,
        client: Redis,
        event_id: int,
        current_reserved_count: int,
    ) -> None:
        # Only track when this is the first ticket (reserved was 0 before)
        if current_reserved_count != 0:
            return

        timer_key = _make_key(f'event_sellout_timer:{event_id}')
        now = datetime.now(timezone.utc).isoformat()

        # Use HSETNX for atomic first-write-wins
        was_set = await cast(
            Awaitable[bool], client.hsetnx(timer_key, 'first_ticket_reserved_at', now)
        )

        # Only record metrics/spans if we actually set the first ticket
        if was_set:
            Logger.base.info(
                f'📊 [SELLOUT-TRACKING] First ticket reserved for event_id={event_id} at {now}'
            )

    @staticmethod
    @Logger.io
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

        timer_key = _make_key(f'event_sellout_timer:{event_id}')

        # Fetch first ticket reserved timestamp
        first_ticket_reserved_at_raw = await cast(
            Awaitable[bytes | str | None], client.hget(timer_key, 'first_ticket_reserved_at')
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
