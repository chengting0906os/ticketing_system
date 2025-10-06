from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from src.service.ticketing.domain.entity.booking_entity import Booking


if TYPE_CHECKING:
    pass


class IBookingCommandRepo(ABC):
    """Repository interface for booking write operations"""

    @abstractmethod
    async def create(self, *, booking: Booking) -> Booking:
        pass

    @abstractmethod
    async def update_status_to_pending_payment(self, *, booking: Booking) -> Booking:
        pass

    @abstractmethod
    async def update_status_to_paid(self, *, booking: Booking) -> Booking:
        pass

    @abstractmethod
    async def update_with_ticket_details(self, *, booking: Booking) -> Booking:
        pass

    @abstractmethod
    async def update_status_to_cancelled(self, *, booking: Booking) -> Booking:
        pass

    @abstractmethod
    async def update_status_to_failed(self, *, booking: Booking) -> Booking:
        pass

    @abstractmethod
    async def update_status_to_completed(self, *, booking: Booking) -> Booking:
        pass

    @abstractmethod
    async def cancel_booking_atomically(self, *, booking_id: int, buyer_id: int) -> Booking:
        pass
