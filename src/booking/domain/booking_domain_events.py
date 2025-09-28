"""
Booking Domain Events

These events are published when booking operations occur and should
be handled by other bounded contexts (like event_ticketing).
"""

from typing import List
import attrs
from datetime import datetime

# Domain events implement MqDomainEvent protocol through duck typing


@attrs.define
class BookingPaidEvent:
    """Published when a booking is successfully paid"""

    booking_id: int
    buyer_id: int
    event_id: int
    ticket_ids: List[int]
    paid_at: datetime
    total_amount: float

    @property
    def aggregate_id(self) -> int:
        return self.booking_id

    @property
    def occurred_at(self) -> datetime:
        return self.paid_at

    @property
    def event_type(self) -> str:
        return 'booking.paid'


@attrs.define
class BookingCancelledEvent:
    """Published when a booking is cancelled"""

    booking_id: int
    buyer_id: int
    event_id: int
    ticket_ids: List[int]
    cancelled_at: datetime

    @property
    def aggregate_id(self) -> int:
        return self.booking_id

    @property
    def occurred_at(self) -> datetime:
        return self.cancelled_at

    @property
    def event_type(self) -> str:
        return 'booking.cancelled'
