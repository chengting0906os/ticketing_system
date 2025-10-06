from abc import ABC, abstractmethod
from typing import List, Optional

from src.service.ticketing.domain.entity.booking_entity import Booking
from src.shared_kernel.domain.value_object.ticket_ref import TicketRef


class IBookingQueryRepo(ABC):
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
    async def get_tickets_by_booking_id(self, *, booking_id: int) -> List['TicketRef']:
        pass
