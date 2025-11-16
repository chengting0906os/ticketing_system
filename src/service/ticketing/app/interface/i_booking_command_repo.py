from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List

from uuid_utils import UUID

from src.service.ticketing.domain.entity.booking_entity import Booking
from src.service.ticketing.domain.value_object.ticket_ref import TicketRef


if TYPE_CHECKING:
    pass


class IBookingCommandRepo(ABC):
    """Repository interface for booking write operations"""

    @abstractmethod
    async def get_by_id(self, *, booking_id: UUID) -> Booking | None:
        """
        Get single booking by ID (for validation before command operations)

        Args:
            booking_id: Booking ID

        Returns:
            Booking entity or None if not found
        """
        pass

    @abstractmethod
    async def get_tickets_by_booking_id(self, *, booking_id: UUID) -> List[TicketRef]:
        """
        Get tickets associated with booking (for command operations)

        Args:
            booking_id: Booking ID

        Returns:
            List of ticket references
        """
        pass

    @abstractmethod
    async def update_status_to_cancelled(self, *, booking: Booking) -> Booking:
        """
        Update booking status to CANCELLED

        Args:
            booking: Booking entity with CANCELLED status

        Returns:
            Updated booking entity
        """
        pass

    @abstractmethod
    async def update_status_to_failed(self, *, booking: Booking) -> None:
        pass

    @abstractmethod
    async def complete_booking_and_mark_tickets_sold_atomically(
        self, *, booking: Booking, ticket_ids: list[int]
    ) -> Booking:
        """
        Atomically update booking to COMPLETED and mark tickets as SOLD in single transaction

        Args:
            booking: Booking entity with COMPLETED status
            ticket_ids: List of ticket IDs to mark as SOLD

        Returns:
            Updated booking entity
        """
        pass

    @abstractmethod
    async def create_booking_with_tickets_directly(
        self,
        *,
        booking_id: UUID,
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
        This method is called by Seat Reservation Service after successful Kvrocks reservation.

        Flow:
        1. Create booking record (status=PENDING_PAYMENT, total_price, seat_positions)
        2. Update ticket records (status=RESERVED) with buyer_id
        Both in single CTE transaction, returns both booking and tickets.

        Args:
            booking_id: UUID7 booking ID (from CreateBookingUseCase)
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

        Raises:
            DomainError: If booking already exists or transaction fails
        """
        pass
