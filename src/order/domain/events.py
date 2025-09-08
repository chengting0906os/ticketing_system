"""Domain Events for Order Aggregate."""

from datetime import datetime
from typing import Optional, Protocol, runtime_checkable

import attrs


@runtime_checkable
class DomainEventProtocol(Protocol):
    @property
    def aggregate_id(self) -> int: ...

    @property
    def occurred_at(self) -> datetime: ...


@attrs.define(frozen=True)
class DomainEvent:
    aggregate_id: int
    occurred_at: datetime = attrs.field(factory=datetime.now)


@attrs.define(frozen=True)
class OrderCreatedEvent:
    aggregate_id: int
    buyer_id: int
    seller_id: int
    product_id: int
    price: int
    occurred_at: datetime = attrs.field(factory=datetime.now)


@attrs.define(frozen=True)
class OrderPaidEvent:
    aggregate_id: int
    buyer_id: int
    product_id: int
    paid_at: datetime
    occurred_at: datetime = attrs.field(factory=datetime.now)


@attrs.define(frozen=True)
class OrderCancelledEvent:
    aggregate_id: int
    buyer_id: int
    product_id: int
    reason: Optional[str] = None
    occurred_at: datetime = attrs.field(factory=datetime.now)


@attrs.define(frozen=True)
class ProductReservedEvent:
    aggregate_id: int
    product_id: int
    order_id: int
    occurred_at: datetime = attrs.field(factory=datetime.now)


@attrs.define(frozen=True)
class ProductReleasedEvent:
    aggregate_id: int
    product_id: int
    order_id: int
    occurred_at: datetime = attrs.field(factory=datetime.now)
