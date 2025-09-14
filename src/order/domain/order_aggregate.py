from datetime import datetime
from typing import TYPE_CHECKING, List

import attrs

from src.order.domain.events import (
    DomainEventProtocol,
    OrderCancelledEvent,
    OrderCreatedEvent,
    OrderPaidEvent,
)
from src.order.domain.order_entity import Order, OrderStatus
from src.order.domain.value_objects import BuyerInfo, SellerInfo, TicketSnapshot
from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger
from src.user.domain.user_entity import UserRole


if TYPE_CHECKING:
    from src.user.domain.user_model import User
    from src.ticket.domain.ticket_entity import Ticket


@attrs.define
class OrderAggregate:
    order: Order
    ticket_snapshots: List['TicketSnapshot']
    buyer_info: BuyerInfo
    seller_info: SellerInfo
    _events: List[DomainEventProtocol] = attrs.field(factory=list, init=False)

    @classmethod
    @Logger.io
    def create_order(
        cls,
        buyer: 'User',
        tickets: List['Ticket'],
        seller: 'User',
    ) -> 'OrderAggregate':
        if buyer.role != UserRole.BUYER.value:
            raise DomainError('Only buyers can create orders', 403)

        if not tickets:
            raise DomainError('No tickets provided', 400)

        # Get event info from first ticket (validation already done in use case)
        event_id = tickets[0].event_id

        # Verify buyer doesn't own any of the events
        if any(ticket.buyer_id != buyer.id for ticket in tickets):
            raise DomainError('All tickets must be reserved by this buyer', 403)

        # Calculate total price from all tickets
        total_price = sum(ticket.price for ticket in tickets)

        order = Order.create(
            buyer_id=buyer.id,
            seller_id=seller.id,
            event_id=event_id,
            total_price=total_price,
        )

        # Create ticket snapshots for order history
        ticket_snapshots = [TicketSnapshot.from_ticket(ticket) for ticket in tickets]

        buyer_info = BuyerInfo.from_user(buyer)
        seller_info = SellerInfo.from_user(seller)

        aggregate = cls(
            order=order,
            ticket_snapshots=ticket_snapshots,
            buyer_info=buyer_info,
            seller_info=seller_info,
        )

        return aggregate

    @Logger.io
    def emit_creation_events(self) -> None:
        if not self.order.id:
            raise ValueError('Order must have an ID before emitting events')

        # Get event info from first ticket (all tickets are same event)
        first_ticket = self.ticket_snapshots[0] if self.ticket_snapshots else None
        event_id = first_ticket.event_id if first_ticket else 0

        self._add_event(
            OrderCreatedEvent(
                aggregate_id=self.order.id,
                buyer_id=self.order.buyer_id,
                seller_id=self.order.seller_id,
                event_id=event_id,
                price=self.order.total_price,
                buyer_email=self.buyer_info.email,
                buyer_name=self.buyer_info.name,
                seller_email=self.seller_info.email,
                seller_name=self.seller_info.name,
                event_name=f'Order for {len(self.ticket_snapshots)} tickets',  # We can improve this later
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

        self._add_event(
            OrderPaidEvent(
                aggregate_id=self.order.id or 0,
                buyer_id=self.order.buyer_id,
                event_id=self.order.event_id,
                paid_at=self.order.paid_at or datetime.now(),
                # Rich data to avoid N+1 queries
                buyer_email=self.buyer_info.email,
                event_name=f'Event {self.order.event_id}',
                paid_amount=self.order.total_price,
            )
        )

    @Logger.io
    def cancel(self) -> None:
        if self.order.status == OrderStatus.PAID:
            raise DomainError('Cannot cancel paid order', 400)
        if self.order.status == OrderStatus.CANCELLED:
            raise DomainError('Order already cancelled', 400)
        self.order = self.order.cancel()

        self._add_event(
            OrderCancelledEvent(
                aggregate_id=self.order.id or 0,
                buyer_id=self.order.buyer_id,
                event_id=self.order.event_id,
                buyer_email=self.buyer_info.email,
                event_name=f'Event {self.order.event_id}',
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
