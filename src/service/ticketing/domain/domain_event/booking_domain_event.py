"""
Booking Domain Events

These events are published when booking operations occur and should
be handled by other bounded contexts (like reservation service).
"""

import attrs
from uuid_utils import UUID

from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus


@attrs.define
class BookingCreatedDomainEvent:
    """Domain event fired when a booking is created"""

    booking_id: UUID
    buyer_id: int
    event_id: int
    total_price: int
    section: str
    subsection: int
    quantity: int
    seat_selection_mode: str
    seat_positions: list[str]
    status: BookingStatus

    @classmethod
    def from_booking(cls, *, booking: 'Booking') -> 'BookingCreatedDomainEvent':
        return cls(
            booking_id=booking.id,
            buyer_id=booking.buyer_id,
            event_id=booking.event_id,
            total_price=booking.total_price,
            section=booking.section,
            subsection=booking.subsection,
            quantity=booking.quantity,
            seat_selection_mode=booking.seat_selection_mode,
            seat_positions=booking.seat_positions or [],
            status=booking.status,
        )


@attrs.define
class BookingCancelledEvent:
    """Minimal event - consumer fetches booking details from DB."""

    booking_id: UUID
    event_id: int
    section: str  # for partition calculation
    subsection: int  # for partition calculation
