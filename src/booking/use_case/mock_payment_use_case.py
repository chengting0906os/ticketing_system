import random
import string
from typing import Any, Dict

from fastapi import Depends

from src.booking.domain.booking_entity import BookingStatus
from src.event.domain.event_entity import EventStatus
from src.shared.exception.exceptions import DomainError, ForbiddenError, NotFoundError
from src.shared.logging.loguru_io import Logger
from src.shared.service.unit_of_work import AbstractUnitOfWork, get_unit_of_work


class MockPaymentUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow=uow)

    @Logger.io
    async def pay_booking(self, booking_id: int, buyer_id: int, card_number: str) -> Dict[str, Any]:
        # In a real implementation, card_number would be used for payment processing
        # For mock payment, we just validate it's present
        if not card_number:
            raise DomainError('Card number is required for payment')
        async with self.uow:
            booking = await self.uow.bookings.get_by_id(booking_id=booking_id)
            if not booking:
                raise NotFoundError('Booking not found')
            if booking.buyer_id != buyer_id:
                raise ForbiddenError('Only the buyer can pay for this booking')
            if booking.status == BookingStatus.PAID:
                raise DomainError('Booking already paid')
            elif booking.status == BookingStatus.CANCELLED:
                raise DomainError('Cannot pay for cancelled booking')
            elif booking.status != BookingStatus.PENDING_PAYMENT:
                raise DomainError('Booking is not in a payable state')

            paid_booking = booking.mark_as_paid()
            updated_booking = await self.uow.bookings.update(booking=paid_booking)
            event = await self.uow.events.get_by_id(event_id=booking.event_id)
            if event:
                event.status = EventStatus.SOLD_OUT
                await self.uow.events.update(event=event)

            # Update reserved tickets to sold status when booking is paid
            reserved_tickets = await self.uow.tickets.get_tickets_by_booking_id(
                booking_id=booking_id
            )
            if reserved_tickets:
                # Update all reserved tickets to sold using domain method
                sold_tickets = []
                for ticket in reserved_tickets:
                    ticket.sell()  # Use the domain method instead of direct assignment
                    sold_tickets.append(ticket)
                await self.uow.tickets.update_batch(tickets=sold_tickets)

            payment_id = (
                f'PAY_MOCK_{"".join(random.choices(string.ascii_uppercase + string.digits, k=8))}'
            )
            await self.uow.commit()

            return {
                'booking_id': updated_booking.id,
                'payment_id': payment_id,
                'status': 'paid',
                'paid_at': updated_booking.paid_at.isoformat() if updated_booking.paid_at else None,
            }

    @Logger.io
    async def cancel_booking(self, booking_id: int, buyer_id: int) -> None:
        async with self.uow:
            cancelled_booking = await self.uow.bookings.cancel_booking_atomically(
                booking_id=booking_id, buyer_id=buyer_id
            )

            await self.uow.events.release_event_atomically(event_id=cancelled_booking.event_id)

            # Release reserved tickets when booking is cancelled
            reserved_tickets = await self.uow.tickets.get_tickets_by_booking_id(
                booking_id=booking_id
            )
            if reserved_tickets:
                # Release all reserved tickets back to available using domain method
                available_tickets = []
                for ticket in reserved_tickets:
                    ticket.release()  # Use the domain method instead of direct assignment
                    available_tickets.append(ticket)
                await self.uow.tickets.update_batch(tickets=available_tickets)

            await self.uow.commit()
