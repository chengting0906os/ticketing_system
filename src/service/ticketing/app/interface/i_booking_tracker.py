"""
Booking Tracker Interface

Prevents duplicate bookings by tracking event_id:buyer_id:booking_id in Kvrocks.
Used for idempotency control in the booking creation flow.
"""

from abc import ABC, abstractmethod
from uuid import UUID


class IBookingTracker(ABC):
    @abstractmethod
    async def track_booking(self, *, event_id: UUID, buyer_id: UUID, booking_id: UUID) -> bool:
        pass

    @abstractmethod
    async def remove_booking_track(
        self, *, event_id: UUID, buyer_id: UUID, booking_id: UUID
    ) -> None:
        pass
