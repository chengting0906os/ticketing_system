"""
Seat State Command Handler Implementation

CQRS Command Side implementation for seat state management.
"""

import os
from typing import Dict, List, Optional

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.shared_kernel.app.interface import ISeatStateCommandHandler


# Get key prefix from environment for test isolation
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')


def _make_key(key: str) -> str:
    """Add prefix to key for test isolation in parallel testing"""
    return f'{_KEY_PREFIX}{key}'


# Status constants
SEAT_STATUS_AVAILABLE = 0  # 00
SEAT_STATUS_RESERVED = 1  # 01
SEAT_STATUS_SOLD = 2  # 10

STATUS_TO_BITFIELD = {
    'available': SEAT_STATUS_AVAILABLE,
    'reserved': SEAT_STATUS_RESERVED,
    'sold': SEAT_STATUS_SOLD,
}


class SeatStateCommandHandlerImpl(ISeatStateCommandHandler):
    """
    Seat State Command Handler Implementation (CQRS Command)

    Responsibility: Only handles write operations, modifying seat state.
    """

    @staticmethod
    def _calculate_seat_index(row: int, seat_num: int, seats_per_row: int) -> int:
        """Calculate seat index in Bitfield"""
        return (row - 1) * seats_per_row + (seat_num - 1)

    @Logger.io
    async def _get_section_config(self, event_id: int, section_id: str) -> Dict:
        """Get section configuration from Redis"""
        try:
            client = kvrocks_client.get_client()
            config_key = _make_key(f'section_config:{event_id}:{section_id}')
            config = await client.hgetall(config_key)  # type: ignore

            if not config:
                raise ValueError(f'Section config not found: {section_id}')

            return {'rows': int(config['rows']), 'seats_per_row': int(config['seats_per_row'])}

        except Exception as e:
            Logger.base.error(f'❌ [CMD] Failed to get section config: {e}')
            raise

    @Logger.io
    async def reserve_seats_atomic(
        self,
        *,
        event_id: int,
        booking_id: str,
        buyer_id: int,
        mode: str,
        seat_ids: Optional[List[str]] = None,
        section: Optional[str] = None,
        subsection: Optional[int] = None,
        quantity: Optional[int] = None,
    ) -> Dict:
        """
        Atomically reserve seats - Using Pipeline (partition guarantees ordering)

        Since Kafka partition key is section-subsection, requests for the same area
        are processed serially, so we don't need Lua script atomic protection.
        Pipeline is sufficient.

        Supports two modes:
        1. manual: Reserve specified seats
        2. best_available: Automatically find and reserve consecutive seats

        Returns:
            {
                'success': bool,
                'reserved_seats': List[str],  # Format: 'section-subsection-row-seat'
                'seat_prices': Dict[str, int],  # seat_id -> price
                'total_price': int,
                'error_message': Optional[str]
            }
        """
        Logger.base.info(f'🎯 [CMD] Reserving seats (mode={mode}) for booking {booking_id}')

        if mode == 'manual':
            return await self._reserve_manual_seats(
                event_id=event_id,
                booking_id=booking_id,
                buyer_id=buyer_id,
                section=section,
                subsection=subsection,
                seat_ids=seat_ids,
            )
        elif mode == 'best_available':
            return await self._reserve_best_available_seats(
                event_id=event_id,
                booking_id=booking_id,
                buyer_id=buyer_id,
                section=section,
                subsection=subsection,
                quantity=quantity,
            )
        else:
            return {
                'success': False,
                'reserved_seats': [],
                'seat_prices': {},
                'total_price': 0,
                'error_message': f'Invalid mode: {mode}',
            }

    async def _reserve_manual_seats(
        self,
        *,
        event_id: int,
        booking_id: str,
        buyer_id: int,
        section: Optional[str],
        subsection: Optional[int],
        seat_ids: Optional[List[str]],
    ) -> Dict:
        """Reserve specified seats - Manual Mode"""
        if not seat_ids or not section or subsection is None:
            return {
                'success': False,
                'reserved_seats': [],
                'seat_prices': {},
                'total_price': 0,
                'error_message': 'Manual mode requires seat_ids, section, and subsection',
            }

        client = kvrocks_client.get_client()
        section_id = f'{section}-{subsection}'

        # Get section config
        config = await self._get_section_config(event_id, section_id)
        seats_per_row = config['seats_per_row']

        # Parse seat positions
        seats_to_reserve = []  # [(row, seat_num, seat_index, seat_id)]
        for seat_id in seat_ids:
            parts = seat_id.split('-')
            if len(parts) == 2:
                row, seat = int(parts[0]), int(parts[1])
                seat_index = self._calculate_seat_index(row, seat, seats_per_row)
                full_seat_id = f'{section}-{subsection}-{row}-{seat}'
                seats_to_reserve.append((row, seat, seat_index, full_seat_id))
            else:
                Logger.base.warning(f'⚠️ Invalid seat format: {seat_id}')

        if not seats_to_reserve:
            return {
                'success': False,
                'reserved_seats': [],
                'seat_prices': {},
                'total_price': 0,
                'error_message': 'No valid seats to reserve',
            }

        # Step 1: Check all seats are available (read phase) - batch check
        bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')
        pipe = client.pipeline()

        for _row, _seat_num, seat_index, _seat_id in seats_to_reserve:
            offset = seat_index * 2  # 2 bits per seat
            pipe.getbit(bf_key, offset)  # Get first bit
            pipe.getbit(bf_key, offset + 1)  # Get second bit

        # Execute all checks at once
        bits_results = await pipe.execute()

        # Validate all seats
        for i, (_row, _seat_num, _seat_index, seat_id) in enumerate(seats_to_reserve):
            bit1 = bits_results[i * 2]
            bit2 = bits_results[i * 2 + 1]
            status = (bit1 << 1) | bit2

            if status != SEAT_STATUS_AVAILABLE:
                return {
                    'success': False,
                    'reserved_seats': [],
                    'seat_prices': {},
                    'total_price': 0,
                    'error_message': f'Seat {seat_id} is not available',
                }

        # Step 2: Reserve all seats (write phase) + get prices
        stats_key = _make_key(f'section_stats:{event_id}:{section_id}')
        reserved_seats = []
        seat_prices = {}

        pipe = client.pipeline()

        for row, seat_num, seat_index, seat_id in seats_to_reserve:
            # Update bitfield: AVAILABLE (00) → RESERVED (01)
            offset = seat_index * 2
            pipe.setbit(bf_key, offset, 0)
            pipe.setbit(bf_key, offset + 1, 1)

            # Get price from seat_meta
            meta_key = _make_key(f'seat_meta:{event_id}:{section_id}:{row}')
            pipe.hget(meta_key, str(seat_num))

            reserved_seats.append(seat_id)

        # Update stats
        num_seats = len(seats_to_reserve)
        pipe.hincrby(stats_key, 'available', -num_seats)
        pipe.hincrby(stats_key, 'reserved', num_seats)

        # Execute pipeline
        results = await pipe.execute()

        # Extract prices from results
        # Results: [setbit, setbit, price, setbit, setbit, price, ..., hincrby, hincrby]
        price_indices = [
            i for i in range(2, len(results) - 2, 3)
        ]  # Every 3rd result starting from index 2
        total_price = 0

        for i, seat_id in enumerate(reserved_seats):
            price_bytes = results[price_indices[i]]
            if price_bytes:
                price = int(price_bytes.decode() if isinstance(price_bytes, bytes) else price_bytes)
                seat_prices[seat_id] = price
                total_price += price
            else:
                # Fallback: price not found in metadata
                seat_prices[seat_id] = 0
                Logger.base.warning(f'⚠️ Price not found for seat {seat_id}')

        Logger.base.info(
            f'✅ [CMD] Reserved {len(reserved_seats)} seats (manual), total: ${total_price}'
        )

        return {
            'success': True,
            'reserved_seats': reserved_seats,
            'seat_prices': seat_prices,
            'total_price': total_price,
            'error_message': None,
        }

    async def _reserve_best_available_seats(
        self,
        *,
        event_id: int,
        booking_id: str,
        buyer_id: int,
        section: Optional[str],
        subsection: Optional[int],
        quantity: Optional[int],
    ) -> Dict:
        """Automatically find and reserve consecutive seats - Best Available Mode"""
        if not section or subsection is None or not quantity:
            return {
                'success': False,
                'reserved_seats': [],
                'seat_prices': {},
                'total_price': 0,
                'error_message': 'Best available mode requires section, subsection, and quantity',
            }

        client = kvrocks_client.get_client()
        section_id = f'{section}-{subsection}'

        # Get section config
        config = await self._get_section_config(event_id, section_id)
        rows = config['rows']
        seats_per_row = config['seats_per_row']

        # Read bitfield to find consecutive seats
        bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')

        # Get entire bitfield
        bitfield_bytes_raw = await client.get(bf_key)

        if not bitfield_bytes_raw:
            return {
                'success': False,
                'reserved_seats': [],
                'seat_prices': {},
                'total_price': 0,
                'error_message': 'Section not initialized',
            }

        # Ensure bitfield is bytes (Redis may return str or bytes)
        if isinstance(bitfield_bytes_raw, str):
            bitfield_bytes = bitfield_bytes_raw.encode('latin-1')
        else:
            bitfield_bytes = bitfield_bytes_raw

        # Find consecutive available seats
        found_seats = []
        for row in range(1, rows + 1):
            consecutive_count = 0
            row_seats = []

            for seat_num in range(1, seats_per_row + 1):
                seat_index = self._calculate_seat_index(row, seat_num, seats_per_row)
                offset = seat_index * 2

                # Extract 2 bits
                byte_index = offset // 8
                bit_offset = offset % 8

                if byte_index < len(bitfield_bytes):
                    byte_val = bitfield_bytes[byte_index]
                    bit1 = (byte_val >> (7 - bit_offset)) & 1
                    bit2 = (byte_val >> (6 - bit_offset)) & 1 if bit_offset < 7 else 0
                    status = (bit1 << 1) | bit2

                    if status == SEAT_STATUS_AVAILABLE:
                        consecutive_count += 1
                        row_seats.append((row, seat_num, seat_index))

                        if consecutive_count == quantity:
                            found_seats = row_seats
                            break
                    else:
                        consecutive_count = 0
                        row_seats = []

            if found_seats:
                break

        if not found_seats:
            return {
                'success': False,
                'reserved_seats': [],
                'seat_prices': {},
                'total_price': 0,
                'error_message': f'No {quantity} consecutive seats available',
            }

        # Reserve found seats
        stats_key = _make_key(f'section_stats:{event_id}:{section_id}')
        reserved_seats = []
        seat_prices = {}

        pipe = client.pipeline()

        for row, seat_num, seat_index in found_seats:
            seat_id = f'{section}-{subsection}-{row}-{seat_num}'

            # Update bitfield
            offset = seat_index * 2
            pipe.setbit(bf_key, offset, 0)
            pipe.setbit(bf_key, offset + 1, 1)

            # Get price
            meta_key = _make_key(f'seat_meta:{event_id}:{section_id}:{row}')
            pipe.hget(meta_key, str(seat_num))

            reserved_seats.append(seat_id)

        # Update stats
        pipe.hincrby(stats_key, 'available', -quantity)
        pipe.hincrby(stats_key, 'reserved', quantity)

        # Execute
        results = await pipe.execute()

        # Extract prices
        price_indices = [i for i in range(2, len(results) - 2, 3)]
        total_price = 0

        for i, seat_id in enumerate(reserved_seats):
            price_bytes = results[price_indices[i]]
            if price_bytes:
                price = int(price_bytes.decode() if isinstance(price_bytes, bytes) else price_bytes)
                seat_prices[seat_id] = price
                total_price += price
            else:
                seat_prices[seat_id] = 0

        Logger.base.info(
            f'✅ [CMD] Reserved {len(reserved_seats)} consecutive seats (best_available), total: ${total_price}'
        )

        return {
            'success': True,
            'reserved_seats': reserved_seats,
            'seat_prices': seat_prices,
            'total_price': total_price,
            'error_message': None,
        }

    async def release_seats(self, seat_ids: List[str], event_id: int) -> Dict[str, bool]:
        """Release seats (RESERVED -> AVAILABLE)"""
        Logger.base.info(f'🔓 [CMD] Releasing {len(seat_ids)} seats')

        # TODO(human): Implement release logic with Lua script
        # Hint: Similar to reserve_seats but change RESERVED -> AVAILABLE
        results = {seat_id: True for seat_id in seat_ids}
        return results

    @Logger.io
    async def finalize_payment(
        self, seat_id: str, event_id: int, timestamp: Optional[str] = None
    ) -> bool:
        """Finalize payment (RESERVED -> SOLD)"""
        Logger.base.info(f'💳 [CMD] Finalizing payment for seat {seat_id}')

        try:
            parts = seat_id.split('-')
            if len(parts) != 4:
                return False

            section, subsection, row, seat_num = parts
            section_id = f'{section}-{subsection}'

            config = await self._get_section_config(event_id, section_id)
            seats_per_row = config['seats_per_row']
            seat_index = self._calculate_seat_index(int(row), int(seat_num), seats_per_row)

            client = kvrocks_client.get_client()
            bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')
            offset = seat_index * 2

            # Set to SOLD (10)
            await client.setbit(bf_key, offset, 0)
            await client.setbit(bf_key, offset + 1, 1)

            Logger.base.info(f'✅ [CMD] Finalized payment for {seat_id}')
            return True

        except Exception as e:
            Logger.base.error(f'❌ [CMD] Failed to finalize payment: {e}')
            return False

    @Logger.io
    async def initialize_seat(
        self, seat_id: str, event_id: int, price: int, timestamp: Optional[str] = None
    ) -> bool:
        """Initialize seat (set to AVAILABLE)"""
        Logger.base.info(f'🆕 [CMD] Initializing seat {seat_id}')

        try:
            parts = seat_id.split('-')
            if len(parts) != 4:
                return False

            section, subsection, row, seat_num = parts
            section_id = f'{section}-{subsection}'

            config = await self._get_section_config(event_id, section_id)
            seats_per_row = config['seats_per_row']
            seat_index = self._calculate_seat_index(int(row), int(seat_num), seats_per_row)

            client = kvrocks_client.get_client()
            bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')
            meta_key = _make_key(f'seat_meta:{event_id}:{section_id}:{row}')
            offset = seat_index * 2

            # Set to AVAILABLE (00)
            await client.setbit(bf_key, offset, 0)
            await client.setbit(bf_key, offset + 1, 0)

            # Set price metadata
            client.hset(meta_key, str(seat_num), str(price))  # pyright: ignore

            Logger.base.info(f'✅ [CMD] Initialized seat {seat_id}')
            return True

        except Exception as e:
            Logger.base.error(f'❌ [CMD] Failed to initialize seat: {e}')
            return False
