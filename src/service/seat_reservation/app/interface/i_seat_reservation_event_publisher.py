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
        event_id: int,
        section: str,
        subsection: int,
        seat_selection_mode: str,
        reserved_seats: List[str],
        seat_prices: dict[str, int],
        total_price: int,
        subsection_stats: dict[str, int],
        event_stats: dict[str, int],
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
