"""
Seat State Reservation Command Handler Interface

CQRS Command Side - Write operations for seat reservation.
"""

from abc import ABC, abstractmethod
from typing import Dict, List


class ISeatStateReservationCommandHandler(ABC):
    """
    Seat State Reservation Command Handler Interface (CQRS Command)

    Responsibility: Seat reservation operations only
    """

    @abstractmethod
    async def find_seats(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        quantity: int,
        rows: int,
        cols: int,
        price: int,
    ) -> Dict:
        """
        Find available seats via Lua script (Step 3 - BEST_AVAILABLE mode).

        Args:
            event_id: Event ID
            section: Section (e.g., 'A')
            subsection: Subsection number (e.g., 1)
            quantity: Number of seats to find
            rows: Number of rows in subsection
            cols: Seats per row
            price: Section price per seat

        Returns:
            Dict with keys:
                - success: bool
                - seats_to_reserve: List[tuple] - [(row, seat_num, seat_index, seat_id), ...]
                - total_price: int
                - error_message: Optional[str]
        """
        pass

    @abstractmethod
    async def verify_seats(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        seat_ids: List[str],
        price: int,
    ) -> Dict:
        """
        Verify specified seats are available via Lua script (Step 3 - MANUAL mode).

        Args:
            event_id: Event ID
            section: Section (e.g., 'A')
            subsection: Subsection number (e.g., 1)
            seat_ids: List of seat IDs to verify (format: "row-seat")
            price: Section price per seat

        Returns:
            Dict with keys:
                - success: bool
                - seats_to_reserve: List[tuple] - [(row, seat_num, seat_index, seat_id), ...]
                - total_price: int
                - error_message: Optional[str]
        """
        pass

    @abstractmethod
    async def update_seat_map(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        booking_id: str,
        seats_to_reserve: List[tuple],
        total_price: int,
    ) -> Dict:
        """
        Update seat map in Kvrocks via Pipeline (Step 5).

        Executes atomic updates: BITFIELD SET for each seat (0 → 1)

        Args:
            event_id: Event ID
            section: Section (e.g., 'A')
            subsection: Subsection number (e.g., 1)
            booking_id: Booking ID
            seats_to_reserve: List of (row, seat_num, seat_index, seat_id) tuples
            total_price: Total price for booking

        Returns:
            Dict with keys:
                - success: bool
                - reserved_seats: List[str]
                - error_message: Optional[str]
        """
        pass
