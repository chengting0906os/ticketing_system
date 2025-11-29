"""
Booking Command Repository Interface (for Reservation Service)

Interface for writing booking data to PostgreSQL.
Reservation Service now handles PostgreSQL writes directly.
"""

from abc import ABC, abstractmethod
from typing import Union

from uuid_utils import UUID

from src.service.ticketing.domain.entity.booking_entity import Booking


class IBookingCommandRepo(ABC):
    """Repository interface for booking write operations in Reservation Service"""

    @abstractmethod
    async def create_booking_and_update_tickets_to_reserved(
        self,
        *,
        booking_id: Union[str, UUID],
        buyer_id: int,
        event_id: int,
        section: str,
        subsection: int,
        seat_selection_mode: str,
        reserved_seats: list[str],
        total_price: int,
    ) -> dict:
        """
        Directly create booking in PENDING_PAYMENT status with tickets in RESERVED status.
        Called after successful Kvrocks reservation.

        Args:
            booking_id: UUID7 booking ID
            buyer_id: Buyer ID
            event_id: Event ID
            section: Section identifier
            subsection: Subsection number
            seat_selection_mode: 'manual' or 'best_available'
            reserved_seats: List of reserved seat identifiers (format: "row-seat")
            total_price: Sum of all seat prices

        Returns:
            Dict with keys:
            - booking: Created/existing booking entity
            - tickets: List of ticket references
        """
        pass

    @abstractmethod
    async def create_failed_booking_directly(
        self,
        *,
        booking_id: Union[str, UUID],
        buyer_id: int,
        event_id: int,
        section: str,
        subsection: int,
        seat_selection_mode: str,
        seat_positions: list[str],
        quantity: int,
    ) -> Booking:
        """
        Directly create booking in FAILED status (no tickets).
        Called when seat reservation fails.

        Args:
            booking_id: UUID7 booking ID
            buyer_id: Buyer ID
            event_id: Event ID
            section: Section identifier
            subsection: Subsection number
            seat_selection_mode: 'manual' or 'best_available'
            seat_positions: Originally requested seat positions
            quantity: Originally requested quantity

        Returns:
            Created booking entity with FAILED status
        """
        pass

    @abstractmethod
    async def complete_booking_and_mark_tickets_sold_atomically(
        self,
        *,
        booking_id: Union[str, UUID],
        ticket_ids: list[int],
    ) -> Booking:
        """
        Atomically update booking to COMPLETED and mark tickets as SOLD.
        Called after payment finalization in Kvrocks.

        Args:
            booking_id: UUID7 booking ID
            ticket_ids: List of ticket IDs to mark as SOLD

        Returns:
            Updated booking entity with COMPLETED status
        """
        pass

    @abstractmethod
    async def update_status_to_cancelled(
        self,
        *,
        booking_id: Union[str, UUID],
    ) -> Booking:
        """
        Update booking status to CANCELLED.
        Called after seat release in Kvrocks.

        Args:
            booking_id: UUID7 booking ID

        Returns:
            Updated booking entity with CANCELLED status
        """
        pass

    @abstractmethod
    async def get_by_id(self, *, booking_id: Union[str, UUID]) -> Booking | None:
        """
        Get booking by ID.

        Args:
            booking_id: UUID7 booking ID

        Returns:
            Booking entity or None if not found
        """
        pass

    @abstractmethod
    async def get_tickets_by_booking_id(self, *, booking_id: Union[str, UUID]) -> list:
        """
        Get all tickets for a booking.

        Args:
            booking_id: UUID7 booking ID

        Returns:
            List of ticket entities
        """
        pass
