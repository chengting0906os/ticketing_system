"""
Seat Finder

Handles finding consecutive available seats using different strategies.

Strategies:
- lua: Use Lua script for atomic find (current default)
- python: Use Python + row_blocks metadata (A/B testing)

Switch via environment variable:
    SEAT_FINDER_STRATEGY=lua|python (default: lua)
"""

import os
from typing import List, Optional

import orjson

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.platform.state.lua_script_executor import lua_script_executor
from src.service.reservation.driven_adapter.reservation_helper.row_block_manager import (
    row_block_manager,
)


# A/B test switch: 'lua' or 'python'
SEAT_FINDER_STRATEGY = os.getenv('SEAT_FINDER_STRATEGY', 'lua')


class SeatFinder:
    """
    Find consecutive available seats using bitfield operations.

    Responsibility: Scan seat bitfields to find N consecutive available seats.
    Supports multiple strategies for A/B testing.
    """

    @staticmethod
    def _calculate_seat_index(row: int, seat_num: int, cols: int) -> int:
        """Calculate seat index in Bitfield"""
        return (row - 1) * cols + (seat_num - 1)

    async def find_consecutive_seats(
        self,
        *,
        bf_key: str,
        rows: int,
        cols: int,
        quantity: int,
        # For Python strategy
        event_id: Optional[int] = None,
        section: Optional[str] = None,
        subsection: Optional[int] = None,
    ) -> Optional[List[tuple]]:
        """
        Find N consecutive available seats.

        Uses strategy based on SEAT_FINDER_STRATEGY environment variable.

        Args:
            bf_key: Bitfield key
            rows: Total number of rows
            cols: Seats per row
            quantity: Number of consecutive seats needed
            event_id: Event ID (required for Python strategy)
            section: Section name (required for Python strategy)
            subsection: Subsection number (required for Python strategy)

        Returns:
            List of (row, seat_num, seat_index) tuples or None if not found
        """
        if SEAT_FINDER_STRATEGY == 'python':
            if event_id is None or section is None or subsection is None:
                Logger.base.warning(
                    '[SEAT-FINDER] Python strategy requires event_id, section, subsection'
                )
                # Fallback to Lua
                return await self._find_via_lua(bf_key, rows, cols, quantity)

            return await self._find_via_python(
                event_id=event_id,
                section=section,
                subsection=subsection,
                quantity=quantity,
                rows=rows,
                cols=cols,
            )
        else:
            return await self._find_via_lua(bf_key, rows, cols, quantity)

    async def _find_via_lua(
        self,
        bf_key: str,
        rows: int,
        cols: int,
        quantity: int,
    ) -> Optional[List[tuple]]:
        """
        Find seats using Lua script (1 network round-trip, early return).

        Pros: Atomic, can early-return when found
        Cons: Logic in Lua, harder to debug/modify
        """
        client = kvrocks_client.get_client()

        try:
            result = await lua_script_executor.find_consecutive_seats(
                client=client,
                keys=[bf_key],
                args=[str(rows), str(cols), str(quantity)],
            )

            if result is None:
                Logger.base.warning(f'[SEAT-FINDER-LUA] No {quantity} consecutive seats found')
                return None

            # Parse JSON result from Lua
            lua_data = orjson.loads(result)
            found_seats = lua_data['seats']
            return [tuple(seat) for seat in found_seats]

        except Exception as e:
            Logger.base.error(f'[SEAT-FINDER-LUA] Script execution failed: {e}')
            raise

    async def _find_via_python(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        quantity: int,
        rows: int,
        cols: int,
    ) -> Optional[List[tuple]]:
        """
        Find seats using Python + row_blocks metadata (1 HGETALL).

        Pros: Logic in Python, easy to debug/modify/test
        Cons: Always reads all row metadata (no early return)
        """
        try:
            result = await row_block_manager.find_consecutive_seats(
                event_id=event_id,
                section=section,
                subsection=subsection,
                quantity=quantity,
                rows=rows,
                cols=cols,
            )

            if result is None:
                Logger.base.warning(f'[SEAT-FINDER-PYTHON] No {quantity} consecutive seats found')
                return None

            Logger.base.debug(f'[SEAT-FINDER-PYTHON] Found {len(result)} seats')
            return result

        except Exception as e:
            Logger.base.error(f'[SEAT-FINDER-PYTHON] Failed: {e}')
            raise


# Global singleton
seat_finder = SeatFinder()
