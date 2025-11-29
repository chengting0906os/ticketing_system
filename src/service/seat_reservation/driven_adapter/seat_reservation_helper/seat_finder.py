"""
Seat Finder

Handles finding consecutive available seats using bitfield operations.
"""

from typing import List, Optional

import orjson

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.platform.state.lua_script_executor import lua_script_executor


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
        Find N consecutive available seats using Lua script (1 network round-trip)

        Args:
            bf_key: Bitfield key
            rows: Total number of rows
            seats_per_row: Seats per row
            quantity: Number of consecutive seats needed

        Returns:
            List of (row, seat_num, seat_index) tuples or None if not found
        """
        client = kvrocks_client.get_client()

        try:
            result = await lua_script_executor.find_consecutive_seats(
                client=client,
                keys=[bf_key],
                args=[str(rows), str(seats_per_row), str(quantity)],
            )

            if result is None:
                Logger.base.warning(f'❌ [SEAT-FINDER-LUA] No {quantity} consecutive seats found')
                return None

            # Parse JSON result from Lua: {"seats": [[row, seat_num, seat_index], ...], ...}
            lua_data = orjson.loads(result)
            found_seats = lua_data['seats']
            found_seats_tuples = [tuple(seat) for seat in found_seats]

            return found_seats_tuples

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-FINDER-LUA] Script execution failed: {e}')
            raise
