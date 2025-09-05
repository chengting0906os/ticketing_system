"""Order entity."""

from datetime import datetime
from enum import Enum
from typing import Optional

import attrs

from src.shared.exceptions import DomainException


class OrderStatus(str, Enum):
    PENDING_PAYMENT = 'pending_payment'
    PAID = 'paid'
    CANCELLED = 'cancelled'
    COMPLETED = 'completed'


def validate_positive_price(instance, attribute, value):
    if value <= 0:
        raise DomainException(status_code=400, message="Price must be positive")


@attrs.define
class Order:
    buyer_id: int = attrs.field(validator=attrs.validators.instance_of(int))
    seller_id: int = attrs.field(validator=attrs.validators.instance_of(int))
    product_id: int = attrs.field(validator=attrs.validators.instance_of(int))
    price: int = attrs.field(validator=[attrs.validators.instance_of(int), validate_positive_price])
    status: OrderStatus = attrs.field(default=OrderStatus.PENDING_PAYMENT, validator=attrs.validators.instance_of(OrderStatus))
    created_at: datetime = attrs.field(factory=datetime.now)
    updated_at: datetime = attrs.field(factory=datetime.now)
    paid_at: Optional[datetime] = None
    id: Optional[int] = None
    
    @classmethod
    def create(cls, buyer_id: int, seller_id: int, product_id: int, price: int) -> 'Order':
        now = datetime.now()
        return cls(
            buyer_id=buyer_id,
            seller_id=seller_id,
            product_id=product_id,
            price=price,
            status=OrderStatus.PENDING_PAYMENT,
            created_at=now,
            updated_at=now,
            paid_at=None,
            id=None
        )
    
    def mark_as_paid(self) -> 'Order':
        """Mark order as paid and set payment timestamp."""
        now = datetime.now()
        return attrs.evolve(
            self,
            status=OrderStatus.PAID,
            paid_at=now,
            updated_at=now
        )

    def cancel(self) -> 'Order':
        """Cancel the order."""
        now = datetime.now()
        return attrs.evolve(
            self,
            status=OrderStatus.CANCELLED,
            updated_at=now
        )
