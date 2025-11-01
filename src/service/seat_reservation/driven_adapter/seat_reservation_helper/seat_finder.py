"""
Seat Finder

Handles finding consecutive available seats using bitfield operations.
"""

import os
from typing import List, Optional

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client


# Get key prefix from environment for test isolation
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')


def _make_key(key: str) -> str:
    """Add prefix to key for test isolation in parallel testing"""
    return f'{_KEY_PREFIX}{key}'


class SeatFinder:
    """
    Find consecutive available seats using bitfield operations

    Responsibility: Scan seat bitfields to find N consecutive available seats
    """

    @staticmethod
    def _calculate_seat_index(row: int, seat_num: int, seats_per_row: int) -> int:
        """Calculate seat index in Bitfield"""
        return (row - 1) * seats_per_row + (seat_num - 1)

    async def find_consecutive_seats(
        self,
        *,
        bf_key: str,
        rows: int,
        seats_per_row: int,
        quantity: int,
    ) -> Optional[List[tuple]]:
        """
        Find N consecutive available seats

        Args:
            bf_key: Bitfield key
            rows: Total number of rows
            seats_per_row: Seats per row
            quantity: Number of consecutive seats needed

        Returns:
            List of (row, seat_num, seat_index) tuples or None if not found
        """
        client = kvrocks_client.get_client()

        Logger.base.debug(
            f'🔍 [SEAT-FINDER] Searching for {quantity} consecutive seats '
            f'(rows={rows}, seats_per_row={seats_per_row})'
        )

        # Scan each row to find consecutive available seats
        for row in range(1, rows + 1):
            consecutive_count = 0
            start_seat = None
            found_seats = []

            for seat_num in range(1, seats_per_row + 1):
                seat_index = self._calculate_seat_index(row, seat_num, seats_per_row)
                offset = seat_index * 2

                # Read 2 bits for seat status
                bit1 = await client.getbit(bf_key, offset)
                bit2 = await client.getbit(bf_key, offset + 1)

                # Status: 00 = AVAILABLE, 01 = RESERVED, 10 = SOLD
                is_available = bit1 == 0 and bit2 == 0

                if is_available:
                    if consecutive_count == 0:
                        start_seat = seat_num
                    consecutive_count += 1
                    found_seats.append((row, seat_num, seat_index))

                    # Found enough consecutive seats
                    if consecutive_count == quantity:
                        Logger.base.debug(
                            f'✅ [SEAT-FINDER] Found {quantity} consecutive seats: '
                            f'row {row}, seats {start_seat}-{seat_num}'
                        )
                        return found_seats
                else:
                    # Reset counter
                    consecutive_count = 0
                    start_seat = None
                    found_seats = []

        Logger.base.warning(f'❌ [SEAT-FINDER] No {quantity} consecutive seats found')
        return None
