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
class BookingCreatedEvent:
    aggregate_id: int
    buyer_id: int
    seller_id: int
    event_id: int
    price: int
    buyer_name: str
    seller_name: str
    event_name: str
    occurred_at: datetime = attrs.field(factory=datetime.now)


@attrs.define(frozen=True)
class BookingPaidEvent:
    aggregate_id: int
    buyer_id: int
    event_id: int
    paid_at: datetime
    event_name: str
    paid_amount: int
    occurred_at: datetime = attrs.field(factory=datetime.now)


@attrs.define(frozen=True)
class BookingCancelledEvent:
    aggregate_id: int
    buyer_id: int
    event_id: int
    event_name: str
    occurred_at: datetime = attrs.field(factory=datetime.now)


@attrs.define(frozen=True)
class EventReservedEvent:
    aggregate_id: int
    event_id: int
    booking_id: int
    occurred_at: datetime = attrs.field(factory=datetime.now)


@attrs.define(frozen=True)
class EventReleasedEvent:
    aggregate_id: int
    event_id: int
    booking_id: int
    occurred_at: datetime = attrs.field(factory=datetime.now)
