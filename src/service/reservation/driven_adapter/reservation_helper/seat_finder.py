"""
Seat Finder

Handles finding consecutive available seats using row_blocks metadata.
"""

from typing import TYPE_CHECKING, List, Optional

from src.platform.logging.loguru_io import Logger

if TYPE_CHECKING:
    from src.service.reservation.driven_adapter.reservation_helper.row_block_manager import (
        RowBlockManager,
    )


class SeatFinder:
    """
    Find consecutive available seats using row_blocks metadata.

    Responsibility: Scan row_blocks to find N consecutive available seats.
    """

    def __init__(self, *, row_block_manager: 'RowBlockManager') -> None:
        self._row_block_manager = row_block_manager

    @staticmethod
    def _calculate_seat_index(row: int, seat_num: int, cols: int) -> int:
        """Calculate seat index in Bitfield"""
        return (row - 1) * cols + (seat_num - 1)

    async def find_consecutive_seats(
        self,
        *,
        rows: int,
        cols: int,
        quantity: int,
        event_id: int,
        section: str,
        subsection: int,
    ) -> Optional[List[tuple]]:
        """
        Find N consecutive available seats using row_blocks metadata.

        Args:
            rows: Total number of rows
            cols: Seats per row
            quantity: Number of consecutive seats needed
            event_id: Event ID
            section: Section name
            subsection: Subsection number

        Returns:
            List of (row, seat_num, seat_index) tuples or None if not found
        """
        try:
            result = await self._row_block_manager.find_consecutive_seats(
                event_id=event_id,
                section=section,
                subsection=subsection,
                quantity=quantity,
                rows=rows,
                cols=cols,
            )

            if result is None:
                Logger.base.warning(f'[SEAT-FINDER] No {quantity} consecutive seats found')
                return None

            Logger.base.debug(f'[SEAT-FINDER] Found {len(result)} seats')
            return result

        except Exception as e:
            Logger.base.error(f'[SEAT-FINDER] Failed: {e}')
            raise
