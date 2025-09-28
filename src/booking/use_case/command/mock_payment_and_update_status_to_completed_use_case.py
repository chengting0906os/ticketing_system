import random
import string
from typing import TYPE_CHECKING, Any, Dict

from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.booking.domain.booking_command_repo import BookingCommandRepo
from src.booking.domain.booking_entity import BookingStatus
from src.booking.domain.booking_query_repo import BookingQueryRepo
from src.event_ticketing.domain.event_command_repo import EventCommandRepo
from src.event_ticketing.domain.event_entity import EventStatus
from src.event_ticketing.domain.event_query_repo import EventQueryRepo
from src.event_ticketing.domain.ticket_command_repo import TicketCommandRepo
from src.shared.config.db_setting import get_async_session
from src.shared.config.di import Container
from src.shared.exception.exceptions import DomainError, ForbiddenError, NotFoundError
from src.shared.logging.loguru_io import Logger


if TYPE_CHECKING:
    from src.booking.infra.booking_command_repo_impl import BookingCommandRepoImpl
    from src.booking.infra.booking_query_repo_impl import BookingQueryRepoImpl


class MockPaymentUseCase:
    def __init__(
        self,
        session: AsyncSession,
        booking_command_repo: BookingCommandRepo,
        booking_query_repo: BookingQueryRepo,
        event_command_repo: EventCommandRepo,
        event_query_repo: EventQueryRepo,
        ticket_command_repo: TicketCommandRepo,
    ):
        self.session = session
        self.booking_command_repo: 'BookingCommandRepoImpl' = booking_command_repo  # pyright: ignore[reportAttributeAccessIssue]
        self.booking_query_repo: 'BookingQueryRepoImpl' = booking_query_repo  # pyright: ignore[reportAttributeAccessIssue]
        self.event_command_repo = event_command_repo
        self.event_query_repo = event_query_repo
        self.ticket_command_repo = ticket_command_repo

    @classmethod
    @inject
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        booking_command_repo: BookingCommandRepo = Depends(Provide[Container.booking_command_repo]),
        booking_query_repo: BookingQueryRepo = Depends(Provide[Container.booking_query_repo]),
        event_command_repo: EventCommandRepo = Depends(Provide[Container.event_command_repo]),
        event_query_repo: EventQueryRepo = Depends(Provide[Container.event_query_repo]),
        ticket_command_repo: TicketCommandRepo = Depends(Provide[Container.ticket_command_repo]),
    ):
        return cls(
            session=session,
            booking_command_repo=booking_command_repo,
            booking_query_repo=booking_query_repo,
            event_command_repo=event_command_repo,
            event_query_repo=event_query_repo,
            ticket_command_repo=ticket_command_repo,
        )

    @Logger.io
    async def pay_booking(self, booking_id: int, buyer_id: int, card_number: str) -> Dict[str, Any]:
        # In a real implementation, card_number would be used for payment processing
        # For mock payment, we just validate it's present
        if not card_number:
            raise DomainError('Card number is required for payment')

        # Get the existing booking
        booking = await self.booking_query_repo.get_by_id(booking_id=booking_id)
        if not booking:
            raise NotFoundError('Booking not found')

        # Validate booking ownership and status
        if booking.buyer_id != buyer_id:
            raise ForbiddenError('Only the buyer can pay for this booking')

        if booking.status == BookingStatus.PAID:
            raise DomainError('Booking already paid')
        elif booking.status == BookingStatus.CANCELLED:
            raise DomainError('Cannot pay for cancelled booking')
        elif booking.status != BookingStatus.PENDING_PAYMENT:
            raise DomainError('Booking is not in a payable state')

        # Process payment and update booking
        paid_booking = booking.mark_as_paid()
        updated_booking = await self.booking_command_repo.update_status_to_paid(
            booking=paid_booking
        )

        # Update event status to sold out
        event = await self.event_query_repo.get_by_id(event_id=booking.event_id)
        if event:
            event.status = EventStatus.SOLD_OUT
            await self.event_command_repo.update(event=event)

        # Update reserved tickets to sold status when booking is paid
        reserved_tickets = await self.booking_query_repo.get_tickets_by_booking_id(
            booking_id=booking_id
        )
        if reserved_tickets:
            # Update all reserved tickets to sold using domain method
            sold_tickets = []
            for ticket in reserved_tickets:
                ticket.sell()  # Use the domain method instead of direct assignment
                sold_tickets.append(ticket)
            await self.ticket_command_repo.update_batch(tickets=sold_tickets)

        # Generate mock payment ID
        payment_id = (
            f'PAY_MOCK_{"".join(random.choices(string.ascii_uppercase + string.digits, k=8))}'
        )

        # Commit the transaction
        await self.session.commit()

        return {
            'booking_id': updated_booking.id,
            'payment_id': payment_id,
            'status': 'paid',
            'paid_at': updated_booking.paid_at.isoformat() if updated_booking.paid_at else None,
        }
