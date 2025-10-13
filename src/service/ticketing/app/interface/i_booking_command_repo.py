from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List

from src.service.ticketing.domain.entity.booking_entity import Booking
from src.service.ticketing.shared_kernel.domain.value_object.ticket_ref import TicketRef


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
    async def update_status_to_pending_payment(self, *, booking: Booking) -> Booking:
        pass

    @abstractmethod
    async def link_tickets_to_booking(self, *, booking_id: int, ticket_ids: list[int]) -> None:
        """Link tickets to a booking by writing to booking_ticket association table"""
        pass

    @abstractmethod
    async def get_ticket_ids_by_booking_id(self, *, booking_id: int) -> list[int]:
        """Get ticket IDs linked to a booking from booking_ticket association table"""
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
