"""
Booking Reservation Event Publisher Interface

Interface for publishing events from Booking Service to Reservation Service.
"""

from abc import ABC, abstractmethod

from src.service.booking.domain.domain_event.reservation_request_event import (
    ReservationRequestEvent,
)


class IBookingReservationEventPublisher(ABC):
    """Interface for publishing booking-to-reservation events via Kafka"""

    @abstractmethod
    async def publish_reservation_request(self, *, event: ReservationRequestEvent) -> None:
        """
        Publish reservation request to Reservation Service.

        Args:
            event: ReservationRequestEvent containing booking info
        """
        pass
