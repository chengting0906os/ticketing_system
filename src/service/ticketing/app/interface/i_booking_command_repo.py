from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List
from uuid import UUID

from src.service.ticketing.domain.entity.booking_entity import Booking
from src.service.ticketing.domain.value_object.ticket_ref import TicketRef


if TYPE_CHECKING:
    pass


class IBookingCommandRepo(ABC):
    """Repository interface for booking write operations"""

    @abstractmethod
    async def get_by_id(self, *, booking_id: UUID) -> Booking | None:
        """
        查詢單筆 booking（用於 command 操作前的驗證）

        Args:
            booking_id: Booking ID

        Returns:
            Booking entity or None if not found
        """
        pass

    @abstractmethod
    async def get_tickets_by_booking_id(self, *, booking_id: UUID) -> List[TicketRef]:
        """
        查詢 booking 關聯的 tickets（用於 command 操作）

        Args:
            booking_id: Booking ID

        Returns:
            List of ticket references
        """
        pass

    @abstractmethod
    async def create(self, *, booking: Booking) -> Booking:
        pass

    @abstractmethod
    async def update_status_to_cancelled(self, *, booking: Booking) -> Booking:
        pass

    @abstractmethod
    async def update_status_to_failed(self, *, booking: Booking) -> Booking:
        pass

    @abstractmethod
    async def complete_booking_and_mark_tickets_sold_atomically(
        self, *, booking: Booking, ticket_ids: list[UUID]
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
    async def reserve_tickets_and_update_booking_atomically(
        self,
        *,
        booking_id: UUID,
        buyer_id: UUID,
        event_id: UUID,
        section: str,
        subsection: int,
        seat_identifiers: list[str],
        ticket_price: int,
    ) -> tuple[Booking, list[TicketRef], int]:
        """
        Atomically reserve tickets and update booking using BATCH statement.

        This method performs N+1 operations in ONE database round-trip using ScyllaDB BATCH:
        1. Update N tickets status to RESERVED and set buyer_id
        2. Update booking status to PENDING_PAYMENT with total_price and seat_positions

        Performance Optimizations:
        - Uses ticket_price from Kvrocks to avoid N SELECT queries for ticket prices
        - Uses BATCH statement to reduce network round-trips from N+1 to 1
        - No LWT needed because Kvrocks Lua script already guaranteed atomicity
        - Single price value because all seats in same subsection have same price

        Args:
            booking_id: Booking ID to update
            buyer_id: Buyer ID for ownership verification
            event_id: Event ID for ticket lookup
            section: Section for ticket lookup
            subsection: Subsection for ticket lookup
            seat_identifiers: List of seat identifiers (format: "row-seat" like ["1-1", "1-2"])
            ticket_price: Price per ticket from Kvrocks (same for all seats in subsection)

        Returns:
            tuple of (updated_booking, reserved_tickets, total_price)

        Raises:
            ValueError: If booking not found or ticket count mismatch
        """
        pass
