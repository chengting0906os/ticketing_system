from typing import Any, Dict, List, Optional

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.event_ticketing.domain.ticket_repo import TicketRepo
from src.shared.config.db_setting import get_async_session
from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger
from src.shared.service.repo_di import get_ticket_repo


class ReserveTicketsUseCase:
    def __init__(
        self,
        session: AsyncSession,
        ticket_repo: TicketRepo,
    ):
        self.session = session
        self.ticket_repo = ticket_repo

    @classmethod
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        ticket_repo: TicketRepo = Depends(get_ticket_repo),
    ):
        return cls(session, ticket_repo)

    @Logger.io
    async def reserve_tickets(
        self, *, event_id: int, ticket_count: int, buyer_id: int, section: str, subsection: int
    ) -> Dict[str, Any]:
        if ticket_count <= 0:
            raise DomainError('Ticket count must be positive', 400)
        if ticket_count > 4:
            raise DomainError('Maximum 4 tickets per booking', 400)

        # Get available tickets for the event (optionally filtered by section/subsection)
        if section or subsection:
            available_tickets = await self.ticket_repo.get_available_tickets_for_section(
                event_id=event_id, section=section, subsection=subsection, limit=ticket_count
            )
        else:
            available_tickets = await self.ticket_repo.get_available_tickets_for_event(
                event_id=event_id, limit=ticket_count
            )

        if len(available_tickets) < ticket_count:
            raise DomainError('Not enough available tickets', 400)

        # Reserve the best available tickets (first n available)
        tickets_to_reserve = available_tickets[:ticket_count]

        # Reserve each ticket
        for ticket in tickets_to_reserve:
            ticket.reserve(buyer_id=buyer_id)

        # Update tickets in database
        await self.ticket_repo.update_batch(tickets=tickets_to_reserve)
        await self.session.commit()

        # Broadcast SSE events for real-time updates
        await self._broadcast_reservation_events_sse(
            event_id=event_id, tickets=tickets_to_reserve, buyer_id=buyer_id
        )

        # Return reservation details
        return {
            'reservation_id': tickets_to_reserve[0].id,  # Use first ticket ID as reservation ID
            'buyer_id': buyer_id,
            'event_id': event_id,
            'ticket_count': ticket_count,
            'status': 'reserved',
            'tickets': [
                {
                    'id': ticket.id,
                    'seat_identifier': ticket.seat_identifier,
                    'price': ticket.price,
                    'section': ticket.section,
                    'subsection': ticket.subsection,
                }
                for ticket in tickets_to_reserve
            ],
        }

    @Logger.io
    async def handle_seat_selection(
        self,
        *,
        mode: str,
        selected_seats: Optional[List[str]] = None,
        quantity: Optional[int] = None,
    ) -> List[int]:
        """Handle seat selection and return list of ticket IDs."""
        if mode == 'manual':
            return await self._handle_manual_seat_selection(selected_seats=selected_seats)
        elif mode == 'best_available':
            return await self._handle_best_available_selection(quantity=quantity)
        else:
            raise DomainError('Invalid seat selection mode', 400)

    async def _handle_manual_seat_selection(
        self, *, selected_seats: Optional[List[str]]
    ) -> List[int]:
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

    async def _handle_best_available_selection(self, *, quantity: Optional[int]) -> List[int]:
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
                        continuous_tickets = self._find_continuous_seats(
                            tickets=row_tickets, quantity=quantity
                        )
                        if continuous_tickets:
                            return [t.id for t in continuous_tickets]

        raise DomainError('No continuous seats available for requested quantity', 400)

    def _find_continuous_seats(self, *, tickets: List, quantity: int) -> List:
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

    @Logger.io
    async def _broadcast_reservation_events_sse(
        self, *, event_id: int, tickets: List, buyer_id: int
    ) -> None:
        """Log ticket reservations (SSE broadcasting removed in favor of simplified implementation)."""
        try:
            # Group tickets by subsection for logging
            subsection_groups = {}
            for ticket in tickets:
                subsection_key = f'{ticket.section}-{ticket.subsection}'
                if subsection_key not in subsection_groups:
                    subsection_groups[subsection_key] = []
                subsection_groups[subsection_key].append(ticket)

            # Log reservation activity
            for subsection_key, subsection_tickets in subsection_groups.items():
                section, subsection = subsection_key.split('-')

                Logger.base.info(
                    f'Reserved {len(subsection_tickets)} tickets '
                    f'in subsection {section}-{subsection} for event {event_id} by buyer {buyer_id}'
                )

            Logger.base.info(
                f'Total reservation: {len(tickets)} tickets for event {event_id} '
                f'affecting {len(subsection_groups)} subsections'
            )

        except Exception as e:
            # Log error but don't fail the reservation
            Logger.base.error(f'Failed to log reservation events: {e}')
            # Continue execution - reservation is already committed to database
