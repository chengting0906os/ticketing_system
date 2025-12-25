"""
Seat State Release Command Handler Interface

CQRS Command Side - Write operations for seat release.
"""

from abc import ABC, abstractmethod
from typing import Dict, List


class ISeatStateReleaseCommandHandler(ABC):
    """
    Seat State Release Command Handler Interface (CQRS Command)

    Responsibility: Seat release operations only
    """

    @abstractmethod
    async def update_seat_map_release(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        booking_id: str,
        seats_to_release: List[tuple],
    ) -> Dict:
        """
        Update seat map in Kvrocks for release via Pipeline.

        Executes atomic updates: BITFIELD SET for each seat (1 → 0)

        Args:
            event_id: Event ID
            section: Section (e.g., 'A')
            subsection: Subsection number (e.g., 1)
            booking_id: Booking ID
            seats_to_release: List of (seat_position, seat_index) tuples

        Returns:
            Dict with keys:
                - success: bool
                - released_seats: List[str]
                - error_message: Optional[str]
        """
        pass
