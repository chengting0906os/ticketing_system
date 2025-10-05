from dataclasses import dataclass
from datetime import datetime
from typing import List

from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus


@dataclass
class BookingCreated:
    """Domain event fired when a booking is created"""

    booking_id: int
    buyer_id: int
    event_id: int
    total_price: int
    section: str
    subsection: int
    quantity: int
    seat_selection_mode: str
    seat_positions: List[str]
    status: BookingStatus
    occurred_at: datetime  # Required by DomainEvent protocol

    @property
    def aggregate_id(self) -> int:
        return self.booking_id

    @classmethod
    def from_booking(cls, booking: 'Booking') -> 'BookingCreated':
        from datetime import datetime, timezone

        return cls(
            booking_id=booking.id,  # type: ignore
            buyer_id=booking.buyer_id,
            event_id=booking.event_id,
            total_price=booking.total_price,
            section=booking.section,
            subsection=booking.subsection,
            quantity=booking.quantity,
            seat_selection_mode=booking.seat_selection_mode,
            seat_positions=booking.seat_positions or [],
            status=booking.status,
            occurred_at=datetime.now(timezone.utc),
        )


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
