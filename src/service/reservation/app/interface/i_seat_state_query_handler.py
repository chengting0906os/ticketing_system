"""
Seat State Query Handler Interface - Reservation Service

CQRS Query Side
Read-only operations for seat availability and status queries
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class ISeatStateQueryHandler(ABC):
    """
    Seat State Query Handler Interface (CQRS Query)

    Responsibility: Read operations only, no state modifications
    """

    @abstractmethod
    async def get_seat_states(self, seat_ids: List[str], event_id: int) -> Dict[str, Dict]:
        """
        Get the states of specified seats

        Args:
            seat_ids: List of seat IDs
            event_id: Event ID

        Returns:
            Dict mapping seat_id to seat state dict with keys:
                - seat_id: str
                - event_id: int
                - status: str ('available', 'reserved', 'sold')
                - price: int
        """
        pass

    @abstractmethod
    async def get_seat_price(self, seat_id: str, event_id: int) -> Optional[int]:
        """
        Get seat price

        Args:
            seat_id: Seat ID
            event_id: Event ID

        Returns:
            Price as int, or None if seat not found
        """
        pass

    @abstractmethod
    async def list_all_subsection_status(self, event_id: int) -> Dict[str, Dict]:
        """
        Get statistics for all subsections of an event

        Args:
            event_id: Event ID

        Returns:
            Dict mapping section_id to stats dict with keys:
                - section_id: str
                - event_id: int
                - available: int
                - reserved: int
                - sold: int
                - total: int
                - updated_at: int
        """
        pass

    @abstractmethod
    async def list_all_subsection_seats(
        self, event_id: int, section: str, subsection: int
    ) -> List[Dict]:
        """
        Get all seats in a specified subsection

        Args:
            event_id: Event ID
            section: Section name (e.g., 'A')
            subsection: Subsection number (e.g., 1)

        Returns:
            List of seat dicts with keys:
                - section: str
                - subsection: int
                - row: int
                - seat_num: int
                - price: int
                - status: str
                - seat_identifier: str
        """
        pass
