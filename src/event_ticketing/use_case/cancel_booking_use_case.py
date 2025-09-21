from typing import Any, Dict

from fastapi import Depends

from src.shared.exception.exceptions import NotFoundError
from src.shared.logging.loguru_io import Logger
from src.shared.service.unit_of_work import AbstractUnitOfWork, get_unit_of_work


class CancelReservationUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow=uow)

    @Logger.io
    async def cancel_booking(self, *, booking_id: int, buyer_id: int) -> Dict[str, Any]:
        async with self.uow:
            # Get the booking first to verify ownership and status
            booking = await self.uow.bookings.get_by_id(booking_id=booking_id)
            if not booking:
                raise NotFoundError('Booking not found')

            # Verify booking belongs to requesting buyer
            if booking.buyer_id != buyer_id:
                from src.shared.exception.exceptions import ForbiddenError

                raise ForbiddenError('Only the buyer can cancel this booking')

            # Check if booking can be cancelled
            from src.booking.domain.booking_entity import BookingStatus

            if booking.status == BookingStatus.PAID:
                from src.shared.exception.exceptions import DomainError

                raise DomainError('Cannot cancel paid booking', 400)
            elif booking.status == BookingStatus.CANCELLED:
                from src.shared.exception.exceptions import DomainError

                raise DomainError('Booking already cancelled', 400)

            # Find tickets by booking_id (now stored in booking.ticket_ids)
            tickets = await self.uow.bookings.get_tickets_by_booking_id(booking_id=booking_id)

            if not tickets:
                raise NotFoundError('Booking not found')

            # Cancel all tickets associated with this booking (release them back to available)
            for ticket in tickets:
                ticket.cancel_reservation(buyer_id=buyer_id)

            # Update booking status to cancelled
            cancelled_booking = booking.cancel()
            await self.uow.bookings.update(booking=cancelled_booking)

            # Update tickets in database
            await self.uow.tickets.update_batch(tickets=tickets)
            await self.uow.commit()

            return {
                'status': 'ok',
                'cancelled_tickets': len(tickets),
            }
