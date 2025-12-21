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
        Find available seats via Lua script (Step 2 of new flow).

        For BEST_AVAILABLE mode: finds consecutive seats.

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
        Verify specified seats are available via Lua script (Step 2 of new flow).

        For MANUAL mode: validates that all specified seats are available.

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
        Update seat map in Kvrocks via Pipeline (Step 4 of new flow).

        Executes atomic updates:
        - BITFIELD SET for each seat (0 → 1)
        - JSON.NUMINCRBY for stats

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
                - subsection_stats: Dict
                - event_stats: Dict
                - error_message: Optional[str]
        """
        pass

    @abstractmethod
    async def release_seats(
        self,
        *,
        booking_id: str,
        seat_positions: List[str],
        event_id: int,
        section: str,
        subsection: int,
    ) -> Dict[str, bool]:
        """
        Release seats (RESERVED -> AVAILABLE) with idempotency control.

        Args:
            booking_id: Booking ID (for idempotency)
            seat_positions: List of seat positions (format: "row-seat", e.g., "1-5")
            event_id: Event ID
            section: Section name (e.g., "A")
            subsection: Subsection number (e.g., 1)

        Returns:
            Dict mapping seat_position to success status

        Note:
            Uses booking metadata to ensure idempotency - if already released,
            returns success without re-releasing (no-op).
        """
        pass
