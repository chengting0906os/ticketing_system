"""Domain Events for Order Aggregate."""

from datetime import datetime
from typing import Protocol, runtime_checkable

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
    buyer_email: str
    buyer_name: str
    seller_email: str
    seller_name: str
    product_name: str
    occurred_at: datetime = attrs.field(factory=datetime.now)


@attrs.define(frozen=True)
class OrderPaidEvent:
    aggregate_id: int
    buyer_id: int
    product_id: int
    paid_at: datetime
    buyer_email: str
    product_name: str
    paid_amount: int
    occurred_at: datetime = attrs.field(factory=datetime.now)


@attrs.define(frozen=True)
class OrderCancelledEvent:
    aggregate_id: int
    buyer_id: int
    product_id: int
    buyer_email: str
    product_name: str
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
