from datetime import datetime
from enum import StrEnum
from typing import List, Optional

import attrs

from src.shared.domain.validators import NumericValidators
from src.shared.logging.loguru_io import Logger


class SeatSelectionMode(StrEnum):
    MANUAL = 'manual'
    BEST_AVAILABLE = 'best_available'


class BookingStatus(StrEnum):
    PROCESSING = 'processing'
    PENDING_PAYMENT = 'pending_payment'
    PAID = 'paid'
    CANCELLED = 'cancelled'
    COMPLETED = 'completed'
    FAILED = 'failed'


# Validation logic moved to shared validators module


@attrs.define
class Booking:
    buyer_id: int = attrs.field(validator=attrs.validators.instance_of(int))
    event_id: int = attrs.field(validator=attrs.validators.instance_of(int))
    total_price: int = attrs.field(
        validator=[attrs.validators.instance_of(int), NumericValidators.validate_positive_price]
    )
    seat_selection_mode: str = attrs.field(validator=attrs.validators.instance_of(str))
    status: BookingStatus = attrs.field(
        default=BookingStatus.PROCESSING, validator=attrs.validators.instance_of(BookingStatus)
    )
    created_at: datetime = attrs.field(factory=datetime.now)
    updated_at: datetime = attrs.field(factory=datetime.now)
    paid_at: Optional[datetime] = None
    ticket_ids: List[int] = attrs.field(factory=list)  # Store ticket IDs in booking
    id: Optional[int] = None

    @classmethod
    @Logger.io
    def create(
        cls,
        *,
        buyer_id: int,
        event_id: int,
        total_price: int,
        seat_selection_mode: str,
        ticket_ids: Optional[List[int]] = None,
    ) -> 'Booking':
        now = datetime.now()
        return cls(
            buyer_id=buyer_id,
            event_id=event_id,
            total_price=total_price,
            seat_selection_mode=seat_selection_mode,
            status=BookingStatus.PROCESSING,
            created_at=now,
            updated_at=now,
            paid_at=None,
            ticket_ids=ticket_ids or [],
            id=None,
        )

    @Logger.io
    def mark_as_pending_payment(self) -> 'Booking':
        now = datetime.now()
        return attrs.evolve(self, status=BookingStatus.PENDING_PAYMENT, updated_at=now)

    @Logger.io
    def mark_as_paid(self) -> 'Booking':
        now = datetime.now()
        return attrs.evolve(self, status=BookingStatus.PAID, paid_at=now, updated_at=now)

    @Logger.io
    def mark_as_failed(self) -> 'Booking':
        now = datetime.now()
        return attrs.evolve(self, status=BookingStatus.FAILED, updated_at=now)

    @Logger.io
    def mark_as_completed(self) -> 'Booking':
        now = datetime.now()
        return attrs.evolve(self, status=BookingStatus.COMPLETED, updated_at=now)

    @Logger.io
    def cancel(self) -> 'Booking':
        now = datetime.now()
        return attrs.evolve(self, status=BookingStatus.CANCELLED, updated_at=now)
