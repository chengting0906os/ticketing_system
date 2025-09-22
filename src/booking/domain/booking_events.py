from dataclasses import dataclass
from datetime import datetime
from typing import List

from src.booking.domain.booking_entity import BookingStatus


@dataclass
class BookingCreated:
    """Domain event fired when a booking is created"""

    booking_id: int
    buyer_id: int
    event_id: int
    seat_selection_mode: str
    ticket_ids: List[int]
    status: BookingStatus
    occurred_at: datetime

    @property
    def aggregate_id(self) -> int:
        return self.booking_id


@dataclass
class BookingStatusChanged:
    """Domain event fired when booking status changes"""

    booking_id: int
    old_status: BookingStatus
    new_status: BookingStatus
    occurred_at: datetime

    @property
    def aggregate_id(self) -> int:
        return self.booking_id


@dataclass
class BookingCancelled:
    """Domain event fired when a booking is cancelled"""

    booking_id: int
    buyer_id: int
    ticket_ids: List[int]
    occurred_at: datetime

    @property
    def aggregate_id(self) -> int:
        return self.booking_id
