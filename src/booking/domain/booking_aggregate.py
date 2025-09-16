from datetime import datetime
from typing import List

import attrs

from src.booking.domain.booking_entity import Booking
from src.booking.domain.events import (
    BookingCancelledEvent,
    BookingCreatedEvent,
    BookingPaidEvent,
    DomainEventProtocol,
)
from src.booking.domain.value_objects import BuyerInfo, SellerInfo, TicketData, TicketSnapshot
from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger


@attrs.define
class BookingAggregate:
    booking: Booking
    ticket_snapshots: List[TicketSnapshot]
    buyer_info: BuyerInfo
    seller_info: SellerInfo
    _events: List[DomainEventProtocol] = attrs.field(factory=list, init=False)

    @classmethod
    @Logger.io
    def create_booking(
        cls,
        buyer_info: BuyerInfo,
        seller_info: SellerInfo,
        ticket_data_list: List[TicketData],
    ) -> 'BookingAggregate':
        # Validate booking domain business rules
        if not ticket_data_list:
            raise DomainError('No tickets provided', 400)

        # Validate maximum 4 tickets per booking
        if len(ticket_data_list) > 4:
            raise DomainError('Maximum 4 tickets per booking', 400)

        # Validate all tickets belong to the same event
        event_ids = {ticket.event_id for ticket in ticket_data_list}
        if len(event_ids) != 1:
            raise DomainError('All tickets must be for the same event', 400)

        # Use Value Objects data
        total_price = sum(ticket.price for ticket in ticket_data_list)
        event_id = ticket_data_list[0].event_id

        booking = Booking.create(
            buyer_id=buyer_info.buyer_id,
            seller_id=seller_info.seller_id,
            event_id=event_id,
            total_price=total_price,
        )

        # Create immutable snapshots for historical record
        ticket_snapshots = [
            TicketSnapshot.from_ticket_data(ticket_data) for ticket_data in ticket_data_list
        ]

        aggregate = cls(
            booking=booking,
            ticket_snapshots=ticket_snapshots,
            buyer_info=buyer_info,
            seller_info=seller_info,
        )

        # Note: Domain events will be created after booking is persisted and has an ID

        return aggregate

    @Logger.io
    def emit_booking_created_event(self) -> None:
        """Emit the booking created event after the booking has an ID"""
        if not self.booking.id:
            raise DomainError('Cannot emit booking created event without booking ID', 400)

        self._events.append(
            BookingCreatedEvent(
                aggregate_id=self.booking.id,
                buyer_id=self.buyer_info.buyer_id,
                seller_id=self.seller_info.seller_id,
                event_id=self.booking.event_id,
                price=self.booking.total_price,
                buyer_email=self.buyer_info.email,
                buyer_name=self.buyer_info.name,
                seller_email=self.seller_info.email,
                seller_name=self.seller_info.name,
                event_name=f'Event {self.booking.event_id}',  # We can improve this later
            )
        )

    @Logger.io
    def pay_booking(self) -> None:
        """Process payment for booking"""
        if self.booking.status != self.booking.status.PENDING_PAYMENT:
            raise DomainError(f'Cannot pay booking with status {self.booking.status}', 400)

        # Update booking status (immutable update)
        paid_booking = self.booking.mark_as_paid()
        self.booking = paid_booking

        self._events.append(
            BookingPaidEvent(
                aggregate_id=self.booking.id or 0,
                buyer_id=self.buyer_info.buyer_id,
                event_id=self.booking.event_id,
                paid_at=self.booking.paid_at or datetime.now(),
                buyer_email=self.buyer_info.email,
                event_name=f'Event {self.booking.event_id}',
                paid_amount=self.booking.total_price,
            )
        )

    @Logger.io
    def cancel_booking(self) -> None:
        """Cancel booking"""
        if self.booking.status == self.booking.status.PAID:
            raise DomainError('Cannot cancel paid booking', 400)

        if self.booking.status == self.booking.status.CANCELLED:
            raise DomainError('Booking already cancelled', 400)

        # Update booking status (immutable update)
        cancelled_booking = self.booking.cancel()
        self.booking = cancelled_booking

        self._events.append(
            BookingCancelledEvent(
                aggregate_id=self.booking.id or 0,
                buyer_id=self.buyer_info.buyer_id,
                event_id=self.booking.event_id,
                buyer_email=self.buyer_info.email,
                event_name=f'Event {self.booking.event_id}',
            )
        )

    @property
    def events(self) -> List[DomainEventProtocol]:
        """Get domain events"""
        return self._events.copy()

    def clear_events(self) -> None:
        """Clear domain events after publishing"""
        self._events.clear()

    @Logger.io
    def get_booking_summary(self) -> dict:
        """Get booking summary including ticket info"""
        # Get event info from first ticket (all tickets are same event)
        first_ticket = self.ticket_snapshots[0] if self.ticket_snapshots else None
        event_id = first_ticket.event_id if first_ticket else 0

        return {
            'booking_id': self.booking.id,
            'buyer_id': self.buyer_info.buyer_id,
            'seller_id': self.seller_info.seller_id,
            'event_id': event_id,
            'total_price': self.booking.total_price,
            'status': self.booking.status.value,
            'ticket_count': len(self.ticket_snapshots),
            'created_at': self.booking.created_at,
            'paid_at': self.booking.paid_at,
        }

    @Logger.io
    def get_booking_details(self) -> dict:
        """Get detailed booking info with tickets"""
        summary = self.get_booking_summary()
        summary.update(
            {
                'buyer_info': {
                    'id': self.buyer_info.buyer_id,
                    'name': self.buyer_info.name,
                    'email': self.buyer_info.email,
                },
                'seller_info': {
                    'id': self.seller_info.seller_id,
                    'name': self.seller_info.name,
                    'email': self.seller_info.email,
                },
                'tickets': [
                    {
                        'ticket_id': ticket.ticket_id,
                        'section': ticket.section,
                        'subsection': ticket.subsection,
                        'row': ticket.row,
                        'seat': ticket.seat,
                        'price': ticket.price,
                        'seat_identifier': ticket.seat_identifier,
                    }
                    for ticket in self.ticket_snapshots
                ],
                'event_name': f'Booking for {len(self.ticket_snapshots)} tickets',  # We can improve this later
            }
        )
        return summary
