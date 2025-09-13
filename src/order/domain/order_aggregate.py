from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

import attrs

from src.order.domain.events import (
    DomainEventProtocol,
    OrderCancelledEvent,
    OrderCreatedEvent,
    OrderPaidEvent,
    EventReleasedEvent,
    EventReservedEvent,
)
from src.order.domain.order_entity import Order, OrderStatus
from src.order.domain.value_objects import BuyerInfo, EventSnapshot, SellerInfo
from src.event.domain.event_entity import Event, EventStatus
from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger
from src.user.domain.user_entity import UserRole


if TYPE_CHECKING:
    from src.user.domain.user_model import User


@attrs.define
class OrderAggregate:
    order: Order
    event_snapshot: EventSnapshot
    buyer_info: BuyerInfo
    seller_info: SellerInfo
    _events: List[DomainEventProtocol] = attrs.field(factory=list, init=False)
    _event: Optional[Event] = attrs.field(default=None, init=False)

    @classmethod
    @Logger.io
    def create_order(
        cls,
        buyer: 'User',
        event: Event,
        seller: 'User',
    ) -> 'OrderAggregate':
        if buyer.role != UserRole.BUYER.value:
            raise DomainError('Only buyers can create orders', 403)
        if buyer.id == event.seller_id:
            raise DomainError('Cannot buy your own event', 403)
        if not event.is_active:
            raise DomainError('Event not active', 400)
        if event.status != EventStatus.AVAILABLE:
            raise DomainError('Event not available', 400)

        order = Order.create(
            buyer_id=buyer.id,
            seller_id=event.seller_id,
            event_id=event.id or 0,
            price=event.price,
        )
        event_snapshot = EventSnapshot.from_event(event)
        buyer_info = BuyerInfo.from_user(buyer)
        seller_info = SellerInfo.from_user(seller)
        aggregate = cls(
            order=order,
            event_snapshot=event_snapshot,
            buyer_info=buyer_info,
            seller_info=seller_info,
        )
        aggregate._event = event
        aggregate._reserve_event()

        return aggregate

    @Logger.io
    def emit_creation_events(self) -> None:
        if not self.order.id:
            raise ValueError('Order must have an ID before emitting events')

        self._add_event(
            OrderCreatedEvent(
                aggregate_id=self.order.id,
                buyer_id=self.order.buyer_id,
                seller_id=self.order.seller_id,
                event_id=self.order.event_id,
                price=self.order.price,
                buyer_email=self.buyer_info.email,
                buyer_name=self.buyer_info.name,
                seller_email=self.seller_info.email,
                seller_name=self.seller_info.name,
                event_name=self.event_snapshot.name,
            )
        )

        if self._event and self._event.status == EventStatus.RESERVED:
            self._add_event(
                EventReservedEvent(
                    aggregate_id=self.order.id,
                    event_id=self._event.id or 0,
                    order_id=self.order.id,
                )
            )

    @Logger.io
    def process_payment(self) -> None:
        if self.order.status != OrderStatus.PENDING_PAYMENT:
            if self.order.status == OrderStatus.PAID:
                raise DomainError('Order already paid', 400)
            elif self.order.status == OrderStatus.CANCELLED:
                raise DomainError('Cannot pay for cancelled order', 400)
            else:
                raise DomainError('Invalid order status for payment', 400)

        self.order = self.order.mark_as_paid()
        if self._event:
            self._event.status = EventStatus.SOLD

        self._add_event(
            OrderPaidEvent(
                aggregate_id=self.order.id or 0,
                buyer_id=self.order.buyer_id,
                event_id=self.order.event_id,
                paid_at=self.order.paid_at or datetime.now(),
                # Rich data to avoid N+1 queries
                buyer_email=self.buyer_info.email,
                event_name=self.event_snapshot.name,
                paid_amount=self.order.price,
            )
        )

    @Logger.io
    def cancel(self) -> None:
        if self.order.status == OrderStatus.PAID:
            raise DomainError('Cannot cancel paid order', 400)
        if self.order.status == OrderStatus.CANCELLED:
            raise DomainError('Order already cancelled', 400)
        self.order = self.order.cancel()
        if self._event and self._event.status == EventStatus.RESERVED:
            self._release_event()

        self._add_event(
            OrderCancelledEvent(
                aggregate_id=self.order.id or 0,
                buyer_id=self.order.buyer_id,
                event_id=self.order.event_id,
                buyer_email=self.buyer_info.email,
                event_name=self.event_snapshot.name,
            )
        )

    @Logger.io
    def _reserve_event(self) -> None:
        if self._event:
            self._event.status = EventStatus.RESERVED

    @Logger.io
    def _release_event(self) -> None:
        if self._event:
            self._event.status = EventStatus.AVAILABLE

            self._add_event(
                EventReleasedEvent(
                    aggregate_id=self.order.id or 0,
                    event_id=self._event.id or 0,
                    order_id=self.order.id or 0,
                )
            )

    @Logger.io
    def _add_event(self, event: DomainEventProtocol) -> None:
        self._events.append(event)

    @Logger.io
    def collect_events(self) -> List[DomainEventProtocol]:
        events = self._events.copy()
        self._events.clear()
        return events

    @Logger.io
    def get_event_for_update(self) -> Optional[Event]:
        return self._event
