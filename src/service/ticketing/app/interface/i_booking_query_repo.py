from abc import ABC, abstractmethod
from typing import List, Optional
from uuid_utils import UUID

from src.service.ticketing.domain.entity.booking_entity import Booking


class IBookingQueryRepo(ABC):
    """Repository interface for booking read operations"""

    @abstractmethod
    async def get_by_id(self, *, booking_id: UUID) -> Optional[Booking]:
        pass

    @abstractmethod
    async def get_by_id_with_details(self, *, booking_id: UUID) -> Optional[dict]:
        """Get booking by ID with full details (event, user info)"""
        pass

    @abstractmethod
    async def get_buyer_bookings_with_details(self, *, buyer_id: int, status: str) -> List[dict]:
        pass

    @abstractmethod
    async def get_seller_bookings_with_details(self, *, seller_id: int, status: str) -> List[dict]:
        pass
