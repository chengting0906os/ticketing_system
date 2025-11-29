"""
Booking Domain Events

These events are published when booking operations occur and should
be handled by other bounded contexts (like event_ticketing).
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

import attrs
from uuid_utils import UUID

from src.service.shared_kernel.domain.value_object import SubsectionConfig
from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus

if TYPE_CHECKING:
    from src.service.ticketing.app.dto import AvailabilityCheckResult


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
    seat_positions: List[str]
    status: BookingStatus
    occurred_at: datetime  # Required by DomainEvent protocol
    # Config for downstream services (avoids redundant Kvrocks lookups)
    config: Optional[SubsectionConfig] = None

    @property
    def aggregate_id(self) -> UUID:
        return self.booking_id

    @classmethod
    def from_booking(cls, booking: 'Booking') -> 'BookingCreatedDomainEvent':
        from datetime import datetime, timezone

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
            occurred_at=datetime.now(timezone.utc),
        )

    @classmethod
    def from_booking_with_config(
        cls, booking: 'Booking', config: 'AvailabilityCheckResult'
    ) -> 'BookingCreatedDomainEvent':
        """Create event with subsection config for downstream services"""

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
            occurred_at=datetime.now(timezone.utc),
            config=config.config,
        )


@attrs.define
class BookingPaidEvent:
    """Published when a booking is successfully paid"""

    booking_id: UUID
    buyer_id: int
    event_id: int
    ticket_ids: List[int]
    paid_at: datetime
    total_amount: float

    @property
    def aggregate_id(self) -> UUID:
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

    booking_id: UUID
    buyer_id: int
    event_id: int
    ticket_ids: List[int]
    seat_positions: List[str]  # Added for seat release
    cancelled_at: datetime

    @property
    def aggregate_id(self) -> UUID:
        return self.booking_id

    @property
    def occurred_at(self) -> datetime:
        return self.cancelled_at

    @property
    def event_type(self) -> str:
        return 'booking.cancelled'
