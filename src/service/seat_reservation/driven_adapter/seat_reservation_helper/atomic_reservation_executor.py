from datetime import datetime, timezone
import os
from typing import Awaitable, Dict, List, cast

import orjson
from redis.asyncio import Redis

from src.platform.state.kvrocks_client import kvrocks_client


# Get key prefix from environment for test isolation
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')


def _make_key(key: str) -> str:
    """Add prefix to key for test isolation in parallel testing"""
    return f'{_KEY_PREFIX}{key}'


class AtomicReservationExecutor:
    @staticmethod
    def _decode_stats(stats_raw: Dict) -> Dict:
        """
        Decode stats from Redis bytes/strings to proper types.

        Redis returns data as bytes or strings depending on configuration.
        This method normalizes the data to Python dict with int values.

        Args:
            stats_raw: Raw stats from Redis (e.g., {b'available': b'100'})

        Returns:
            Dict with decoded integer values (e.g., {'available': 100})
        """
        if not stats_raw:
            return {}

        decoded = {}
        for key, value in stats_raw.items():
            # Handle both bytes and string keys (e.g., b'available' → 'available')
            if isinstance(key, bytes):
                key: str = key.decode()

            # Handle both bytes and string values (e.g., b'100' → '100')
            if isinstance(value, bytes):
                value: str = value.decode()

            # Convert to int (e.g., '100' → 100)
            try:
                decoded[key] = int(value)
            except (ValueError, TypeError):
                decoded[key] = 0

        return decoded

    @staticmethod
    async def _track_sold_out(
        *,
        client,
        event_id: int,
        new_available_count: int,
        total_seats: int,
    ) -> None:
        # Only track if event just sold out
        if new_available_count != 0:
            return

        timer_key: str = _make_key(f'event_sellout_timer:{event_id}')

        # Get first ticket timestamp
        first_ticket_sold_at_bytes = await client.hget(timer_key, 'first_ticket_sold_at')
        first_ticket_sold_at: datetime = datetime.fromisoformat(first_ticket_sold_at_bytes.decode())
        sold_out_at: datetime = datetime.now(timezone.utc)
        duration_seconds: float = (sold_out_at - first_ticket_sold_at).total_seconds()

        # Save sold out info
        await client.hset(
            timer_key,
            mapping={
                'sold_out_at': sold_out_at.isoformat(),
                'duration_seconds': str(duration_seconds),
                'total_seats': str(total_seats),
                'status': 'SOLD_OUT',
            },
        )

    @staticmethod
    async def get_sellout_stats(*, event_id: int) -> Dict:
        client: Redis = kvrocks_client.get_client()
        timer_key = _make_key(f'event_sellout_timer:{event_id}')

        stats_raw = await cast(Awaitable[dict], client.hgetall(timer_key))

        if not stats_raw:
            return {}

        # Decode bytes to strings
        return {key.decode(): value.decode() for key, value in stats_raw.items()}

    async def fetch_seat_prices(
        self,
        *,
        event_id: int,
        section_id: str,
        seats_to_reserve: List[tuple],
    ) -> tuple[Dict[str, int], int]:
        """
        Pre-fetch all seat prices before atomic reservation.

        ## Why Pre-fetch?

        Prices are stored in separate Redis hashes (seat_meta:{event}:{section}:{row}).
        If we fetch them inside the main pipeline, we'd need to:
        1. Execute pipeline
        2. Parse results to extract prices
        3. Calculate total_price
        4. Create another pipeline with total_price

        Instead, we pre-fetch prices in a separate pipeline, which is safe because:
        - Seat prices are READ-ONLY during reservation (they don't change)
        - This doesn't affect consistency (we still verify availability later)

        ## Example

        Input: seats_to_reserve = [(1, 1, 0, 'A-1-1-1'), (1, 2, 1, 'A-1-1-2')]
        Output: ({'A-1-1-1': 1000, 'A-1-1-2': 1000}, 2000)

        Args:
            event_id: Event identifier (e.g., 123)
            section_id: Section identifier (e.g., 'A-1')
            seats_to_reserve: List of (row, seat_num, seat_index, seat_id) tuples
                Example: [(1, 1, 0, 'A-1-1-1'), (1, 2, 1, 'A-1-1-2')]

        Returns:
            Tuple of:
            - seat_prices: Dict mapping seat_id to price (e.g., {'A-1-1-1': 1000})
            - total_price: Sum of all prices (e.g., 2000)
        """
        # Get Redis client (lightweight dict lookup, returns existing connection pool)
        client = kvrocks_client.get_client()
        price_pipe = client.pipeline()

        # Batch fetch all prices in ONE pipeline
        # Example: For seats [(1,1), (1,2)], fetch from:
        #   - seat_meta:123:A-1:1 → field '1'
        #   - seat_meta:123:A-1:1 → field '2'
        for row, seat_num, _, _ in seats_to_reserve:
            meta_key = _make_key(f'seat_meta:{event_id}:{section_id}:{row}')
            price_pipe.hget(meta_key, str(seat_num))

        # Execute pipeline and get results
        # Example result: [b'1000', b'1000']
        price_results = await price_pipe.execute()

        # Calculate total price and build price mapping
        seat_prices = {}
        total_price = 0
        for idx, (_, _, _, seat_id) in enumerate(seats_to_reserve):
            # Convert bytes to int (e.g., b'1000' → 1000)
            price = int(price_results[idx]) if price_results[idx] else 0
            seat_prices[seat_id] = price
            total_price += price

        return seat_prices, total_price

    async def execute_atomic_reservation(
        self,
        *,
        event_id: int,
        section_id: str,
        booking_id: str,
        bf_key: str,
        seats_to_reserve: List[tuple],
        seat_prices: Dict[str, int],
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
            seat_prices: Pre-fetched seat prices (e.g., {'A-1-1-1': 1000, 'A-1-1-2': 1000})
            total_price: Pre-calculated total price (e.g., 2000)

        Returns:
            Dict with reservation results:
            {
                'success': True,
                'reserved_seats': ['A-1-1-1', 'A-1-1-2'],
                'seat_prices': {'A-1-1-1': 1000, 'A-1-1-2': 1000},
                'total_price': 2000,
                'subsection_stats': {'available': 98, 'reserved': 2},
                'event_stats': {'available': 98, 'reserved': 2},
                'error_message': None
            }
        """
        # Get Redis client (lightweight dict lookup)
        client = kvrocks_client.get_client()

        # ========== STEP 0: Get current stats for time tracking ==========
        # We need to know the current reserved count to determine if this is the first ticket
        event_stats_key: str = _make_key(f'event_stats:{event_id}')
        current_stats = await cast(Awaitable[dict], client.hgetall(event_stats_key))
        current_reserved_count = int(current_stats.get(b'reserved', b'0'))
        current_total_seats = int(current_stats.get(b'total', b'0'))

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
        # Update both subsection and event-level statistics atomically
        #
        # Example before:
        # - section_stats:123:A-1 → {available: 100, reserved: 0}
        # - event_stats:123 → {available: 500, reserved: 0}
        #
        # After reserving 2 seats:
        # - section_stats:123:A-1 → {available: 98, reserved: 2}
        # - event_stats:123 → {available: 498, reserved: 2}
        stats_key = _make_key(f'section_stats:{event_id}:{section_id}')
        num_seats = len(seats_to_reserve)

        # Decrement available, increment reserved (atomic counters)
        pipe.hincrby(stats_key, 'available', -num_seats)
        pipe.hincrby(stats_key, 'reserved', num_seats)
        pipe.hincrby(event_stats_key, 'available', -num_seats)
        pipe.hincrby(event_stats_key, 'reserved', num_seats)

        # ========== STEP 3: Fetch updated statistics ==========
        # Get the new stats to include in response and booking metadata
        pipe.hgetall(stats_key)
        pipe.hgetall(event_stats_key)

        # ========== STEP 4: Track first ticket sold timestamp ==========
        # If this is the first reservation, record the timestamp
        # NOTE: This must come AFTER hgetall to maintain consistent pipeline result indices
        if current_reserved_count == 0:
            timer_key = _make_key(f'event_sellout_timer:{event_id}')
            now = datetime.now(timezone.utc).isoformat()
            # HSETNX: Only set if field doesn't exist (atomic, prevents race conditions)
            pipe.hsetnx(timer_key, 'first_ticket_sold_at', now)

        # ========== STEP 5: Save booking metadata ==========
        # Save booking metadata for tracking reservation status
        # Note: We save stats references (keys) here, not the actual stats
        # The actual stats will be decoded from the pipeline results
        booking_key = _make_key(f'booking:{booking_id}')
        pipe.hset(
            booking_key,
            mapping={
                'status': 'RESERVE_SUCCESS',
                'reserved_seats': orjson.dumps(reserved_seats).decode(),
                'seat_prices': orjson.dumps(seat_prices).decode(),
                'total_price': str(total_price),
                'stats_key': stats_key,  # Store keys to fetch stats later if needed
                'event_stats_key': event_stats_key,
            },
        )

        # ========== Execute pipeline (batch all commands) ==========
        # Execute all queued commands in sequence
        # Each individual command (SETBIT, HINCRBY, HSET) is atomic
        # Pipeline reduces network round-trips for better performance
        results = await pipe.execute()

        # ========== Parse statistics from pipeline results ==========
        # Calculate indices based on pipeline structure:
        #
        # Results layout :
        # - [0 to num_seats*2-1]: setbit results (2 per seat)
        # - [num_seats*2 to num_seats*2+3]: hincrby results (4 total)
        # - [num_seats*2+4]: subsection_stats (hgetall)
        # - [num_seats*2+5]: event_stats (hgetall)
        # - [num_seats*2+6]: hsetnx result (optional, only if first ticket)
        # - [num_seats*2+6 or 7]: hset result (booking metadata)
        #
        # Example with 2 seats:
        # - Results[0-3]: 4 setbit results
        # - Results[4-7]: 4 hincrby results
        # - Results[8]: subsection_stats ← (2*2 + 4)
        # - Results[9]: event_stats ← (2*2 + 5)
        # - Results[10]: hsetnx (if first ticket) or hset (if not first)
        # - Results[11]: hset (if first ticket)
        subsection_stats_idx = num_seats * 2 + 4
        event_stats_idx = subsection_stats_idx + 1

        subsection_stats = self._decode_stats(results[subsection_stats_idx])
        event_stats = self._decode_stats(results[event_stats_idx])

        # ========== STEP 6: Track sold out timestamp ==========
        # If event just sold out (available == 0), record timestamp and calculate duration
        await self._track_sold_out(
            client=client,
            event_id=event_id,
            new_available_count=event_stats.get('available', 0),
            total_seats=current_total_seats,
        )

        # Return complete reservation result
        return {
            'success': True,
            'reserved_seats': reserved_seats,
            'seat_prices': seat_prices,
            'total_price': total_price,
            'subsection_stats': subsection_stats,
            'event_stats': event_stats,
            'error_message': None,
        }
