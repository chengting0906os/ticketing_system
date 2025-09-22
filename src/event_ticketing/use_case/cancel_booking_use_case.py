from typing import Any, Dict

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.booking.domain.booking_command_repo import BookingCommandRepo
from src.booking.domain.booking_query_repo import BookingQueryRepo
from src.booking.domain.booking_entity import BookingStatus
from src.event_ticketing.domain.ticket_repo import TicketRepo
from src.shared.config.db_setting import get_async_session
from src.shared.exception.exceptions import NotFoundError
from src.shared.logging.loguru_io import Logger
from src.shared.service.repo_di import (
    get_booking_command_repo,
    get_booking_query_repo,
    get_ticket_repo,
)


class CancelReservationUseCase:
    def __init__(
        self,
        session: AsyncSession,
        booking_command_repo: BookingCommandRepo,
        booking_query_repo: BookingQueryRepo,
        ticket_repo: TicketRepo,
    ):
        self.session = session
        self.booking_command_repo = booking_command_repo
        self.booking_query_repo = booking_query_repo
        self.ticket_repo = ticket_repo

    @classmethod
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        booking_command_repo: BookingCommandRepo = Depends(get_booking_command_repo),
        booking_query_repo: BookingQueryRepo = Depends(get_booking_query_repo),
        ticket_repo: TicketRepo = Depends(get_ticket_repo),
    ):
        return cls(
            session=session,
            booking_command_repo=booking_command_repo,
            booking_query_repo=booking_query_repo,
            ticket_repo=ticket_repo,
        )

    @Logger.io
    async def cancel_booking(self, *, booking_id: int, buyer_id: int) -> Dict[str, Any]:
        # Get the booking first to verify ownership and status
        booking = await self.booking_query_repo.get_by_id(booking_id=booking_id)
        if not booking:
            raise NotFoundError('Booking not found')

        # Verify booking belongs to requesting buyer
        if booking.buyer_id != buyer_id:
            from src.shared.exception.exceptions import ForbiddenError

            raise ForbiddenError('Only the buyer can cancel this booking')

        # Check if booking can be cancelled
        if booking.status == BookingStatus.PAID:
            from src.shared.exception.exceptions import DomainError

            raise DomainError('Cannot cancel paid booking', 400)
        elif booking.status == BookingStatus.CANCELLED:
            from src.shared.exception.exceptions import DomainError

            raise DomainError('Booking already cancelled', 400)

        # Find tickets by booking_id (now stored in booking.ticket_ids)
        tickets = await self.booking_query_repo.get_tickets_by_booking_id(booking_id=booking_id)

        if not tickets:
            raise NotFoundError('Booking not found')

        # Collect event IDs for notification
        event_ids = set()

        # Cancel all tickets associated with this booking (release them back to available)
        for ticket in tickets:
            ticket.cancel_reservation(buyer_id=buyer_id)
            event_ids.add(ticket.event_id)

        # Update booking status to cancelled
        cancelled_booking = booking.cancel()
        await self.booking_command_repo.update_status_to_cancelled(booking=cancelled_booking)

        # Update tickets in database
        await self.ticket_repo.update_batch(tickets=tickets)

        # Notify SSE listeners about ticket status changes for each affected event
        for event_id in event_ids:
            await self.session.execute(
                text(f"NOTIFY ticket_status_change_{event_id}, 'tickets_cancelled'")
            )

        await self.session.commit()

        return {
            'status': 'ok',
            'cancelled_tickets': len(tickets),
        }
