from typing import Any, Dict

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.booking.domain.booking_entity import BookingStatus
from src.booking.domain.booking_repo import BookingRepo
from src.shared.config.db_setting import get_async_session
from src.shared.exception.exceptions import DomainError, ForbiddenError, NotFoundError
from src.shared.logging.loguru_io import Logger
from src.shared.service.repo_di import get_booking_repo


class CancelBookingUseCase:
    def __init__(self, session: AsyncSession, booking_repo: BookingRepo):
        self.session = session
        self.booking_repo = booking_repo

    @classmethod
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        booking_repo: BookingRepo = Depends(get_booking_repo),
    ):
        return cls(session=session, booking_repo=booking_repo)

    @Logger.io
    async def cancel_booking(self, *, booking_id: int, buyer_id: int) -> Dict[str, Any]:
        # Get the booking first to verify ownership and status
        booking = await self.booking_repo.get_by_id(booking_id=booking_id)
        if not booking:
            raise NotFoundError('Booking not found')

        # Verify booking belongs to requesting buyer
        if booking.buyer_id != buyer_id:
            raise ForbiddenError('Only the buyer can cancel this booking')

        # Check if booking can be cancelled
        if booking.status == BookingStatus.PAID:
            raise DomainError('Cannot cancel paid booking', 400)
        elif booking.status == BookingStatus.CANCELLED:
            raise DomainError('Booking already cancelled', 400)

        # Cancel the booking
        cancelled_booking = booking.cancel()
        await self.booking_repo.update(booking=cancelled_booking)
        await self.session.commit()

        # TODO: Emit BookingCancelled domain event for event_ticketing domain to handle ticket release
        # This should be handled by an event handler that listens to BookingCancelled events
        # and releases the associated tickets back to available status

        return {
            'status': 'ok',
            'cancelled_tickets': len(booking.ticket_ids),
        }
