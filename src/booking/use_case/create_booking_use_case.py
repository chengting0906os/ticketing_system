from typing import List, Optional

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.booking.domain.booking_aggregate import BookingAggregate
from src.booking.domain.booking_entity import Booking
from src.booking.domain.booking_repo import BookingRepo
from src.event.domain.event_repo import EventRepo
from src.shared.config.db_setting import get_async_session
from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger
from src.shared.service.repo_di import (
    get_booking_repo,
    get_event_repo,
    get_ticket_repo,
    get_user_repo,
)
from src.event.domain.ticket_repo import TicketRepo
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
        buyer_id: int,
        ticket_ids: Optional[List[int]] = None,
        seat_selection_mode: Optional[str] = None,
        selected_seats: Optional[List[str]] = None,
        quantity: Optional[int] = None,
    ) -> Booking:
        # Handle different booking modes
        if seat_selection_mode:
            ticket_ids = await self._handle_seat_selection(
                seat_selection_mode, selected_seats, quantity
            )
        elif ticket_ids is None:
            raise DomainError(
                'Either ticket_ids or seat selection parameters must be provided', 400
            )

        # Validate maximum 4 tickets per booking
        if len(ticket_ids) > 4:
            raise DomainError('Maximum 4 tickets per booking', 400)
        if len(ticket_ids) == 0:
            raise DomainError('At least 1 ticket required', 400)

        buyer = await self.user_repo.get_by_id(user_id=buyer_id)
        if not buyer:
            raise DomainError('Buyer not found', 404)

        # Get tickets by IDs
        tickets = []
        for ticket_id in ticket_ids:
            ticket = await self.ticket_repo.get_by_id(ticket_id=ticket_id)
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

        event, seller = await self.event_repo.get_by_id_with_seller(event_id=event_id)
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

        # Create Value Objects for BookingAggregate
        from src.booking.domain.value_objects import BuyerInfo, SellerInfo, TicketData

        buyer_info = BuyerInfo.from_user(buyer)
        seller_info = SellerInfo.from_user(seller)
        ticket_data_list = [TicketData.from_ticket(ticket) for ticket in tickets]

        # Create booking using BookingAggregate
        aggregate = BookingAggregate.create_booking(buyer_info, seller_info, ticket_data_list)
        created_booking = await self.booking_repo.create(booking=aggregate.booking)
        aggregate.booking.id = created_booking.id

        # Emit domain events now that we have a booking ID
        aggregate.emit_booking_created_event()

        # Update tickets with booking_id and reserved status
        for ticket in tickets:
            ticket.booking_id = created_booking.id
        await self.ticket_repo.update_batch(tickets=tickets)

        # Domain events are created but not processed (email notifications removed)

        # Commit the transaction
        await self.session.commit()

        return created_booking

    async def _handle_seat_selection(
        self, mode: str, selected_seats: Optional[List[str]] = None, quantity: Optional[int] = None
    ) -> List[int]:
        """Handle seat selection and return list of ticket IDs."""
        if mode == 'manual':
            return await self._handle_manual_seat_selection(selected_seats)
        elif mode == 'best_available':
            return await self._handle_best_available_selection(quantity)
        else:
            raise DomainError('Invalid seat selection mode', 400)

    async def _handle_manual_seat_selection(self, selected_seats: Optional[List[str]]) -> List[int]:
        """Handle manual seat selection and return ticket IDs."""
        if not selected_seats or len(selected_seats) == 0:
            raise DomainError('Selected seats cannot be empty for manual selection', 400)
        if len(selected_seats) > 4:
            raise DomainError('Maximum 4 tickets per booking', 400)

        ticket_ids = []
        event_ids = set()

        for seat in selected_seats:
            try:
                section, subsection_str, row_str, seat_str = seat.split('-')
                subsection = int(subsection_str)
                row = int(row_str)
                seat_num = int(seat_str)
            except (ValueError, AttributeError):
                raise DomainError(
                    'Invalid seat format. Expected: section-subsection-row-seat (e.g., A-1-1-1)',
                    400,
                )

            # Find ticket by seat location
            # Note: In the current system structure, we need to search through all available tickets
            # This is a simplified approach for the minimal implementation
            all_tickets = await self.ticket_repo.get_all_available()
            matching_ticket = None

            for ticket in all_tickets:
                if (
                    ticket.section == section
                    and ticket.subsection == subsection
                    and ticket.row == row
                    and ticket.seat == seat_num
                    and ticket.status.value == 'available'
                ):
                    matching_ticket = ticket
                    event_ids.add(ticket.event_id)
                    break

            if not matching_ticket:
                raise DomainError(f'Seat {seat} is not available', 400)

            ticket_ids.append(matching_ticket.id)

        # Validate all seats are from same event
        if len(event_ids) > 1:
            raise DomainError('All tickets must be for the same event', 400)

        return ticket_ids

    async def _handle_best_available_selection(self, quantity: Optional[int]) -> List[int]:
        """Handle best available seat selection and return ticket IDs."""
        if not quantity or quantity <= 0:
            raise DomainError('Quantity must be positive for best available selection', 400)
        if quantity > 4:
            raise DomainError('Maximum 4 tickets per booking', 400)

        # Get all available tickets
        all_tickets = await self.ticket_repo.get_all_available()

        if not all_tickets:
            raise DomainError('No tickets available', 400)

        # Group tickets by event, section, subsection, and row
        tickets_by_event = {}
        for ticket in all_tickets:
            if ticket.status.value == 'available':
                event_id = ticket.event_id
                if event_id not in tickets_by_event:
                    tickets_by_event[event_id] = {}

                section = ticket.section
                if section not in tickets_by_event[event_id]:
                    tickets_by_event[event_id][section] = {}

                subsection = ticket.subsection
                if subsection not in tickets_by_event[event_id][section]:
                    tickets_by_event[event_id][section][subsection] = {}

                row = ticket.row
                if row not in tickets_by_event[event_id][section][subsection]:
                    tickets_by_event[event_id][section][subsection][row] = []

                tickets_by_event[event_id][section][subsection][row].append(ticket)

        # Find continuous seats - prioritize lower row numbers
        for event_id in tickets_by_event:
            for section in tickets_by_event[event_id]:
                for subsection in tickets_by_event[event_id][section]:
                    # Sort rows by number (ascending)
                    rows = sorted(tickets_by_event[event_id][section][subsection].keys())

                    for row in rows:
                        row_tickets = tickets_by_event[event_id][section][subsection][row]
                        # Sort tickets by seat number
                        row_tickets.sort(key=lambda t: t.seat)

                        # Find continuous sequence of requested quantity
                        continuous_tickets = self._find_continuous_seats(row_tickets, quantity)
                        if continuous_tickets:
                            return [t.id for t in continuous_tickets]

        raise DomainError('No continuous seats available for requested quantity', 400)

    def _find_continuous_seats(self, tickets: List, quantity: int) -> List:
        """Find continuous seats in a row."""
        if len(tickets) < quantity:
            return []

        for i in range(len(tickets) - quantity + 1):
            # Check if seats are continuous
            continuous = True
            for j in range(1, quantity):
                if tickets[i + j].seat != tickets[i + j - 1].seat + 1:
                    continuous = False
                    break

            if continuous:
                return tickets[i : i + quantity]

        return []
