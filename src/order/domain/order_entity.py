from datetime import datetime
from enum import Enum
from typing import Optional

import attrs

from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger


class OrderStatus(str, Enum):
    PENDING_PAYMENT = 'pending_payment'
    PAID = 'paid'
    CANCELLED = 'cancelled'
    COMPLETED = 'completed'


@Logger.io
def validate_positive_price(instance, attribute, value):
    if value <= 0:
        raise DomainError('Price must be positive', 400)


@attrs.define
class Order:
    buyer_id: int = attrs.field(validator=attrs.validators.instance_of(int))
    seller_id: int = attrs.field(validator=attrs.validators.instance_of(int))
    event_id: int = attrs.field(validator=attrs.validators.instance_of(int))
    price: int = attrs.field(validator=[attrs.validators.instance_of(int), validate_positive_price])
    status: OrderStatus = attrs.field(
        default=OrderStatus.PENDING_PAYMENT, validator=attrs.validators.instance_of(OrderStatus)
    )
    created_at: datetime = attrs.field(factory=datetime.now)
    updated_at: datetime = attrs.field(factory=datetime.now)
    paid_at: Optional[datetime] = None
    id: Optional[int] = None

    @classmethod
    @Logger.io
    def create(cls, buyer_id: int, seller_id: int, event_id: int, price: int) -> 'Order':
        now = datetime.now()
        return cls(
            buyer_id=buyer_id,
            seller_id=seller_id,
            event_id=event_id,
            price=price,
            status=OrderStatus.PENDING_PAYMENT,
            created_at=now,
            updated_at=now,
            paid_at=None,
            id=None,
        )

    @Logger.io
    def mark_as_paid(self) -> 'Order':
        now = datetime.now()
        return attrs.evolve(self, status=OrderStatus.PAID, paid_at=now, updated_at=now)

    @Logger.io
    def cancel(self) -> 'Order':
        now = datetime.now()
        return attrs.evolve(self, status=OrderStatus.CANCELLED, updated_at=now)
