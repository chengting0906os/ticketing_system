"""
Seat State Query Handler Interface - Shared Kernel

Seat State Query Handler Interface - CQRS Query Side
Used by both Ticketing and Seat Reservation bounded contexts
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class ISeatStateQueryHandler(ABC):
    """
    Seat State Query Handler Interface (CQRS Query)

    Responsibility: Only handles read operations, does not modify state
    """

    @abstractmethod
    async def get_seat_states(self, seat_ids: List[str], event_id: int) -> Dict[str, Dict]:
        """
        Get the state of specified seats

        Args:
            seat_ids: List of seat IDs
            event_id: Event ID

        Returns:
            Dict mapping seat_id to seat state
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
            Seat price, None if seat does not exist
        """
        pass

    @abstractmethod
    async def list_all_subsection_status(self, event_id: int) -> Dict[str, Dict]:
        """
        Get statistics for all subsections of an event

        Args:
            event_id: Event ID

        Returns:
            Dict mapping section_id to stats:
            {
                "A-1": {"available": 100, "reserved": 20, "sold": 30, "total": 150},
                ...
            }
        """
        pass

    @abstractmethod
    async def list_all_subsection_seats(
        self, event_id: int, section: str, subsection: int
    ) -> List[Dict]:
        """
        Get all seats in a specified subsection (including available, reserved, sold)

        Args:
            event_id: Event ID
            section: Section code
            subsection: Subsection number

        Returns:
            List of seats, each containing section, subsection, row, seat_num, price, status, seat_identifier
        """
        pass
