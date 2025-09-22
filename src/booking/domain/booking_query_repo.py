from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional

from src.booking.domain.booking_entity import Booking


if TYPE_CHECKING:
    from src.event_ticketing.domain.ticket_entity import Ticket


class BookingQueryRepo(ABC):
    """Repository interface for booking read operations"""

    @abstractmethod
    async def get_by_id(self, *, booking_id: int) -> Optional[Booking]:
        pass

    @abstractmethod
    async def get_buyer_bookings_with_details(self, *, buyer_id: int, status: str) -> List[dict]:
        pass

    @abstractmethod
    async def get_seller_bookings_with_details(self, *, seller_id: int, status: str) -> List[dict]:
        pass

    @abstractmethod
    async def get_tickets_by_booking_id(self, *, booking_id: int) -> List['Ticket']:
        pass
