from typing import List, Optional

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.booking.domain.booking_aggregate import BookingAggregate
from src.booking.domain.booking_entity import Booking
from src.booking.domain.booking_repo import BookingRepo
from src.event_ticketing.domain.event_repo import EventRepo
from src.event_ticketing.domain.ticket_repo import TicketRepo
from src.shared.config.db_setting import get_async_session
from src.shared.event_bus.ticket_event_publisher import publish_booking_created_by_subsections
from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger
from src.shared.service.repo_di import (
    get_booking_repo,
    get_event_repo,
    get_ticket_repo,
    get_user_repo,
)
from src.user.domain.user_repo import UserRepo


class CreateBookingUseCase:
    def __init__(
        self,
        session: AsyncSession,
        booking_repo: BookingRepo,
        user_repo: UserRepo,
        ticket_repo: TicketRepo,
        event_repo: EventRepo,
    ):
        self.session = session
        self.booking_repo = booking_repo
        self.user_repo = user_repo
        self.ticket_repo = ticket_repo
        self.event_repo = event_repo

    @classmethod
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        booking_repo: BookingRepo = Depends(get_booking_repo),
        user_repo: UserRepo = Depends(get_user_repo),
        ticket_repo: TicketRepo = Depends(get_ticket_repo),
        event_repo: EventRepo = Depends(get_event_repo),
    ):
        return cls(session, booking_repo, user_repo, ticket_repo, event_repo)

    @Logger.io
    async def create_booking(
        self,
        *,
        buyer_id: int,
        ticket_ids: Optional[List[int]] = None,
        seat_selection_mode: Optional[str] = None,
        selected_seats: Optional[List[str]] = None,
        quantity: Optional[int] = None,
    ) -> Booking:
        # Validate input approaches
        approaches_used = 0
        if ticket_ids is not None:
            approaches_used += 1
        if seat_selection_mode is not None:
            approaches_used += 1

        if approaches_used == 0:
            raise DomainError('Must provide either ticket_ids or seat_selection_mode', 400)
        elif approaches_used > 1:
            raise DomainError('Cannot mix ticket_ids with seat selection mode', 400)

        # Validate seat selection parameters
        if seat_selection_mode == 'manual':
            if not selected_seats or len(selected_seats) == 0:
                raise DomainError('selected_seats is required for manual selection', 400)
            if quantity is not None:
                raise DomainError('Cannot specify both selected_seats and quantity', 400)
            if len(selected_seats) > 4:
                raise DomainError('Maximum 4 tickets per booking', 400)
        elif seat_selection_mode == 'best_available':
            if quantity is None:
                raise DomainError('quantity is required for best_available selection', 400)
            if selected_seats is not None:
                raise DomainError('Cannot specify selected_seats for best_available selection', 400)
            if quantity < 1 or quantity > 4:
                raise DomainError('Quantity must be between 1 and 4', 400)

        # Validate legacy ticket_ids approach
        if ticket_ids is not None:
            if len(ticket_ids) > 4:
                raise DomainError('Maximum 4 tickets per booking', 400)
            if len(ticket_ids) == 0:
                raise DomainError('At least 1 ticket required', 400)

        buyer = await self.user_repo.get_by_id(user_id=buyer_id)
        if not buyer:
            raise DomainError('Buyer not found', 404)

        # Convert seat selection to ticket_ids if needed
        if seat_selection_mode == 'manual':
            # Find tickets by seat identifiers (e.g., "A-1-1-1")
            ticket_ids = []
            for seat_identifier in selected_seats:  # type: ignore
                parts = seat_identifier.split('-')
                if len(parts) != 4:
                    raise DomainError(f'Invalid seat format: {seat_identifier}', 400)

                section, subsection, row, seat = parts
                try:
                    subsection_int = int(subsection)
                    row_int = int(row)
                    seat_int = int(seat)
                except ValueError:
                    raise DomainError(f'Invalid seat format: {seat_identifier}', 400)

                # Find ticket by seat location
                ticket = await self.ticket_repo.get_by_seat_location(
                    section=section,
                    subsection=subsection_int,
                    row_number=row_int,
                    seat_number=seat_int,
                )
                if not ticket:
                    raise DomainError(f'Seat {seat_identifier} not found', 404)
                if ticket.status.value != 'available':
                    raise DomainError(f'Seat {seat_identifier} is not available', 400)
                ticket_ids.append(ticket.id)  # type: ignore

        elif seat_selection_mode == 'best_available':
            # Find best available consecutive seats
            # For now, just get the first available seats (simplified implementation)
            available_tickets = await self.ticket_repo.get_available_tickets_limit(limit=quantity)  # type: ignore
            if len(available_tickets) < quantity:  # type: ignore
                raise DomainError(
                    f'Not enough available seats. Requested: {quantity}, Available: {len(available_tickets)}',
                    400,
                )
            ticket_ids = [ticket.id for ticket in available_tickets[:quantity]]  # type: ignore

        # Get tickets by IDs
        tickets = []
        for ticket_id in ticket_ids:  # type: ignore
            ticket = await self.ticket_repo.get_by_id(ticket_id=ticket_id)
            if ticket:
                tickets.append(ticket)

        if len(tickets) != len(ticket_ids):  # type: ignore
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

        event, seller = await self.event_repo.get_by_id_with_seller(event_id=event_id)
        if not event:
            raise DomainError('Event not found', 404)
        if not seller:
            raise DomainError('Seller not found', 404)

        # Validate event is available for booking
        if not event.is_active:
            raise DomainError('Event not active', 400)

        # Reserve tickets for this buyer
        for ticket in tickets:
            ticket.reserve(buyer_id=buyer_id)

        # Create Value Objects for BookingAggregate
        from src.booking.domain.value_objects import BuyerInfo, SellerInfo, TicketData

        buyer_info = BuyerInfo.from_user(buyer)
        seller_info = SellerInfo.from_user(seller)
        ticket_data_list = [TicketData.from_ticket(ticket) for ticket in tickets]

        # Create booking using BookingAggregate
        aggregate = BookingAggregate.create_booking(
            buyer_info=buyer_info, seller_info=seller_info, ticket_data_list=ticket_data_list
        )
        created_booking = await self.booking_repo.create(booking=aggregate.booking)
        aggregate.booking.id = created_booking.id

        # Emit domain events now that we have a booking ID
        aggregate.emit_booking_created_event()

        # Update tickets with booking_id and reserved status
        for ticket in tickets:
            ticket.booking_id = created_booking.id
        await self.ticket_repo.update_batch(tickets=tickets)

        # Commit the database transaction
        await self.session.commit()

        # Publish domain events after successful commit using section-based partitioning
        try:
            await publish_booking_created_by_subsections(booking_aggregate=aggregate)
        except Exception as e:
            # Log error but don't fail the booking - events can be retried
            Logger.base.error(f'Failed to publish booking events: {e}')

        # Clear events after publishing
        aggregate.clear_events()

        return created_booking
