from typing import List

from fastapi import Depends

from src.booking.domain.booking_aggregate import BookingAggregate
from src.booking.domain.booking_entity import Booking
from src.booking.use_case.mock_send_email_use_case import MockSendEmailUseCase
from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger
from src.shared.service.mock_email_service import MockEmailService, get_mock_email_service
from src.shared.service.unit_of_work import AbstractUnitOfWork, get_unit_of_work


class CreateBookingUseCase:
    def __init__(self, uow: AbstractUnitOfWork, email_service: MockEmailService):
        self.uow = uow
        self.email_service = email_service
        self.email_use_case = MockSendEmailUseCase(email_service)

    @classmethod
    def depends(
        cls,
        uow: AbstractUnitOfWork = Depends(get_unit_of_work),
        email_service: MockEmailService = Depends(get_mock_email_service),
    ):
        return cls(uow, email_service)

    @Logger.io
    async def create_booking(self, buyer_id: int, ticket_ids: List[int]) -> Booking:
        async with self.uow:
            # Validate maximum 4 tickets per booking
            if len(ticket_ids) > 4:
                raise DomainError('Maximum 4 tickets per booking', 400)
            if len(ticket_ids) == 0:
                raise DomainError('At least 1 ticket required', 400)

            buyer = await self.uow.users.get_by_id(user_id=buyer_id)
            if not buyer:
                raise DomainError('Buyer not found', 404)

            # Get tickets by IDs
            tickets = []
            for ticket_id in ticket_ids:
                ticket = await self.uow.tickets.get_by_id(ticket_id=ticket_id)
                if ticket:
                    tickets.append(ticket)

            if len(tickets) != len(ticket_ids):
                raise DomainError('Some tickets not found', 404)

            # Validate all tickets are available and can be reserved
            for ticket in tickets:
                if ticket.status.value != 'available':
                    raise DomainError('All tickets must be available', 400)
                if ticket.buyer_id is not None:
                    raise DomainError('Tickets are already reserved', 400)
                if ticket.booking_id is not None:
                    raise DomainError('Tickets are already in a booking', 400)

            # Get event info from first ticket (all should be same event)
            event_id = tickets[0].event_id
            if not all(ticket.event_id == event_id for ticket in tickets):
                raise DomainError('All tickets must be for the same event', 400)

            event, seller = await self.uow.events.get_by_id_with_seller(event_id=event_id)
            if not event:
                raise DomainError('Event not found', 404)
            if not seller:
                raise DomainError('Seller not found', 404)

            # Validate event is available for bookinging
            if not event.is_active:
                raise DomainError('Event not active', 400)
            # Note: Event status (available/sold_out/ended) doesn't prevent booking
            # Individual ticket availability is checked separately

            # Reserve tickets for this buyer
            for ticket in tickets:
                ticket.reserve(buyer_id=buyer_id)

            # Create booking using BookingAggregate
            aggregate = BookingAggregate.create_booking(buyer, tickets, seller)
            created_booking = await self.uow.bookings.create(booking=aggregate.booking)
            aggregate.booking.id = created_booking.id

            # Update tickets with booking_id and reserved status
            for ticket in tickets:
                ticket.booking_id = created_booking.id
            await self.uow.tickets.update_batch(tickets=tickets)

            aggregate.emit_creation_events()
            events = aggregate.collect_events()
            for event in events:
                await self.email_use_case.handle_notification(event)

            await self.uow.commit()

        return created_booking
