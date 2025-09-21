from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional

from src.booking.domain.booking_entity import Booking

if TYPE_CHECKING:
    from src.event_ticketing.domain.ticket_entity import Ticket


class BookingRepo(ABC):
    @abstractmethod
    async def create(self, *, booking: Booking) -> Booking:
        pass

    @abstractmethod
    async def get_by_id(self, *, booking_id: int) -> Optional[Booking]:
        pass

    @abstractmethod
    async def get_by_event_id(self, *, event_id: int) -> Optional[Booking]:
        pass

    @abstractmethod
    async def get_by_buyer(self, *, buyer_id: int) -> List[Booking]:
        pass

    @abstractmethod
    async def get_by_seller(self, *, seller_id: int) -> List[Booking]:
        pass

    @abstractmethod
    async def update(self, *, booking: Booking) -> Booking:
        pass

    @abstractmethod
    async def cancel_booking_atomically(self, *, booking_id: int, buyer_id: int) -> Booking:
        pass

    @abstractmethod
    async def get_buyer_bookings_with_details(self, *, buyer_id: int, status: str) -> List[dict]:
        pass

    @abstractmethod
    async def get_seller_bookings_with_details(self, *, seller_id: int, status: str) -> List[dict]:
        pass

    @abstractmethod
    async def get_tickets_by_booking_id(self, *, booking_id: int) -> List['Ticket']:
        """Get all tickets for a booking using the ticket_ids stored in the booking"""
        pass
