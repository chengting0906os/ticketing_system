from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List

from src.service.ticketing.domain.entity.booking_entity import Booking
from src.service.ticketing.domain.value_object.ticket_ref import TicketRef


if TYPE_CHECKING:
    pass


class IBookingCommandRepo(ABC):
    """Repository interface for booking write operations"""

    @abstractmethod
    async def get_by_id(self, *, booking_id: int) -> Booking | None:
        """
        查詢單筆 booking（用於 command 操作前的驗證）

        Args:
            booking_id: Booking ID

        Returns:
            Booking entity or None if not found
        """
        pass

    @abstractmethod
    async def get_tickets_by_booking_id(self, *, booking_id: int) -> List[TicketRef]:
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
    async def reserve_tickets_and_update_booking_atomically(
        self,
        *,
        booking_id: int,
        buyer_id: int,
        event_id: int,
        section: str,
        subsection: int,
        seat_identifiers: list[str],
    ) -> tuple[Booking, list[TicketRef], int]:
        """
        Atomically reserve tickets and update booking in a single CTE operation.

        This method performs 3 operations in ONE database round-trip using PostgreSQL CTE:
        1. Query and validate tickets by seat_identifiers
        2. Update tickets status to RESERVED and set buyer_id
        3. Update booking status to PENDING_PAYMENT with total_price and seat_positions

        Performance: Reduces 5 database round-trips to 1 by using CTE.

        Args:
            booking_id: Booking ID to update
            buyer_id: Buyer ID for ownership verification
            event_id: Event ID for ticket lookup
            section: Section for ticket lookup
            subsection: Subsection for ticket lookup
            seat_identifiers: List of seat identifiers (format: "row-seat" like ["1-1", "1-2"])

        Returns:
            tuple of (updated_booking, reserved_tickets, total_price)

        Raises:
            ValueError: If booking not found or ticket count mismatch
            ForbiddenError: If buyer_id doesn't match booking owner
        """
        pass
