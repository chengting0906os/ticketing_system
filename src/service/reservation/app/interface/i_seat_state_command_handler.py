"""
Seat State Command Handler Interface

CQRS Command Side - Write operations for seat state changes.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class ISeatStateCommandHandler(ABC):
    """
    Seat State Command Handler Interface (CQRS Command)

    Responsibility: Write operations only, modifies state
    """

    @abstractmethod
    async def reserve_seats_atomic(
        self,
        *,
        event_id: int,
        booking_id: str,
        buyer_id: int,
        mode: str,  # 'manual' or 'best_available'
        section: str,  # Required, not Optional
        subsection: int,  # Required, not Optional
        quantity: int,  # Required, not Optional
        seat_ids: Optional[List[str]] = None,  # for manual mode
        # Config from upstream (avoids redundant Kvrocks lookups in Lua scripts)
        rows: Optional[int] = None,
        cols: Optional[int] = None,
        price: Optional[int] = None,
    ) -> Dict:
        """
        Atomically reserve seats - Unified interface, Lua script routes based on mode

        Args:
            event_id: Event ID
            booking_id: Booking ID
            buyer_id: Buyer ID
            mode: Reservation mode ('manual' or 'best_available')
            section: Section (e.g., 'A') - Required
            subsection: Subsection number (e.g., 1) - Required
            quantity: Number of seats - Required
            seat_ids: List of seat IDs for manual mode (Optional, only for manual mode)
            rows: Number of rows in subsection (Optional, from upstream cache)
            cols: Seats per row (Optional, from upstream cache)
            price: Section price per seat (Optional, from upstream cache)

        Returns:
            Dict with keys:
                - success: bool
                - reserved_seats: List[str] (List of seat IDs)
                - error_message: Optional[str]
        """
        pass

    @abstractmethod
    async def release_seats(self, seat_ids: List[str], event_id: int) -> Dict[str, bool]:
        """
        Release seats (RESERVED -> AVAILABLE)

        Args:
            seat_ids: List of seat IDs
            event_id: Event ID

        Returns:
            Dict mapping seat_id to success status
        """
        pass

    @abstractmethod
    async def finalize_payment(self, *, seat_id: str, event_id: int) -> bool:
        """
        Complete payment, change seat from RESERVED to SOLD

        Config (cols) is fetched from Kvrocks internally.

        Args:
            seat_id: Seat ID (format: section-subsection-row-seat)
            event_id: Event ID

        Returns:
            Success status
        """
        pass
