"""
Seat Reservation Event Publisher Interface

Defines the abstraction for publishing seat reservation events.
"""

from abc import ABC, abstractmethod
from typing import List


class ISeatReservationEventPublisher(ABC):
    """Seat reservation event publisher interface"""

    @abstractmethod
    async def publish_seats_reserved(
        self,
        *,
        booking_id: str,
        buyer_id: int,
        reserved_seats: List[str],
        total_price: int,
        event_id: int,
    ) -> None:
        """Publish seat reservation success event"""
        pass

    @abstractmethod
    async def publish_reservation_failed(
        self,
        *,
        booking_id: str,
        buyer_id: int,
        error_message: str,
        event_id: int,
    ) -> None:
        """Publish seat reservation failure event"""
        pass
