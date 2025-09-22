"""Shared seat selection logic for ticket booking."""

from typing import Dict, List, Optional

from src.event_ticketing.domain.ticket_repo import TicketRepo
from src.shared.domain.validators import BusinessRuleValidators
from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger


class SeatSelectionService:
    """Service for handling seat selection operations."""

    def __init__(self, ticket_repo: TicketRepo):
        self.ticket_repo = ticket_repo

    @Logger.io
    async def handle_seat_selection(
        self,
        *,
        mode: str,
        seat_positions: Optional[List[str]] = None,
        quantity: Optional[int] = None,
    ) -> List[int]:
        """Handle seat selection and return list of ticket IDs."""
        if mode == 'manual':
            return await self._handle_manual_seat_selection(seat_positions=seat_positions)
        elif mode == 'best_available':
            return await self._handle_best_available_selection(quantity=quantity)
        else:
            raise DomainError('Invalid seat selection mode. Use "manual" or "best_available"', 400)

    async def _handle_manual_seat_selection(
        self, *, seat_positions: Optional[List[str]]
    ) -> List[int]:
        """Handle manual seat selection and return ticket IDs."""
        if not seat_positions:
            raise DomainError('Selected seats cannot be empty for manual selection', 400)

        BusinessRuleValidators.validate_ticket_count(len(seat_positions))

        ticket_ids = []
        event_ids = set()

        for seat_identifier in seat_positions:
            section, subsection, row, seat = BusinessRuleValidators.validate_seat_identifier_format(
                seat_identifier
            )

            # Find ticket by seat location
            ticket = await self.ticket_repo.get_by_seat_location(  # type: ignore[attr-defined]
                section=section, subsection=subsection, row_number=row, seat_number=seat
            )

            if not ticket:
                raise DomainError(f'Seat {seat_identifier} not found', 404)

            if ticket.status.value != 'available':
                raise DomainError(f'Seat {seat_identifier} is not available', 400)

            event_ids.add(ticket.event_id)
            ticket_ids.append(ticket.id)

        # Validate all seats are from same event
        if len(event_ids) > 1:
            raise DomainError('All tickets must be for the same event', 400)

        return ticket_ids

    async def _handle_best_available_selection(self, *, quantity: Optional[int]) -> List[int]:
        """Handle best available seat selection and return ticket IDs."""
        if not quantity:
            raise DomainError('Quantity is required for best_available selection', 400)

        BusinessRuleValidators.validate_ticket_count(quantity)

        # Get all available tickets
        all_tickets = await self.ticket_repo.get_all_available()

        if not all_tickets:
            raise DomainError('No tickets available', 400)

        # Group tickets by event, section, subsection, and row for optimal selection
        tickets_by_location = self._group_tickets_by_location(all_tickets)

        # Find the best continuous seats
        best_tickets = self._find_best_continuous_seats(tickets_by_location, quantity)

        if not best_tickets:
            raise DomainError('No continuous seats available for requested quantity', 400)

        return [ticket.id for ticket in best_tickets]

    def _group_tickets_by_location(self, tickets: List) -> Dict:
        """Group tickets by event, section, subsection, and row."""
        tickets_by_event = {}

        for ticket in tickets:
            if ticket.status.value != 'available':
                continue

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

        return tickets_by_event

    def _find_best_continuous_seats(
        self, tickets_by_location: Dict, quantity: int
    ) -> Optional[List]:
        """Find the best continuous seats from grouped tickets."""
        # Priority: lower event ID, then section alphabetically, then lower subsection, then lower row
        for event_id in sorted(tickets_by_location.keys()):
            for section in sorted(tickets_by_location[event_id].keys()):
                for subsection in sorted(tickets_by_location[event_id][section].keys()):
                    rows = sorted(tickets_by_location[event_id][section][subsection].keys())

                    for row in rows:
                        row_tickets = tickets_by_location[event_id][section][subsection][row]
                        row_tickets.sort(key=lambda t: t.seat)

                        continuous_tickets = self._find_continuous_seats_in_row(
                            tickets=row_tickets, quantity=quantity
                        )

                        if continuous_tickets:
                            return continuous_tickets

        return None

    def _find_continuous_seats_in_row(self, *, tickets: List, quantity: int) -> Optional[List]:
        """Find continuous seats in a single row."""
        if len(tickets) < quantity:
            return None

        for i in range(len(tickets) - quantity + 1):
            # Check if seats are continuous
            continuous = True
            for j in range(1, quantity):
                if tickets[i + j].seat != tickets[i + j - 1].seat + 1:
                    continuous = False
                    break

            if continuous:
                return tickets[i : i + quantity]

        return None
