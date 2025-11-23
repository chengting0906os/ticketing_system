"""
Event Ticketing Aggregate - Aggregate Root for Event Ticketing

[DDD Design Principles]
- EventTicketingAggregate is the Aggregate Root
- Event and Ticket are entities within the aggregate
- All ticketing operations go through the aggregate root
- Ensures transactional consistency and business rules

[Business Invariants]
- Event must have valid seating configuration
- Ticket count must match seating configuration
- Ticket status changes must follow business rules
- Event status and ticket status must remain consistent
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

import attrs

from src.platform.logging.loguru_io import Logger
from src.service.ticketing.domain.enum.event_status import EventStatus
from src.service.ticketing.domain.enum.ticket_status import TicketStatus


@attrs.define
class Ticket:
    event_id: int
    section: str
    subsection: int
    row: int
    seat: int
    price: int
    status: TicketStatus
    buyer_id: Optional[int] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    reserved_at: Optional[datetime] = None

    @property
    def seat_identifier(self) -> str:
        return f'{self.section}-{self.subsection}-{self.row}-{self.seat}'

    @Logger.io
    def reserve(self, *, buyer_id: int) -> None:
        if self.status != TicketStatus.AVAILABLE:
            raise ValueError(f'Cannot reserve ticket with status {self.status}')

        self.status = TicketStatus.RESERVED
        self.buyer_id = buyer_id
        self.reserved_at = datetime.now(timezone.utc)

    @Logger.io
    def sell(self) -> None:
        if self.status != TicketStatus.RESERVED:
            raise ValueError(f'Cannot sell ticket with status {self.status}')

        self.status = TicketStatus.SOLD

    @Logger.io
    def release(self) -> None:
        if self.status != TicketStatus.RESERVED:
            raise ValueError(f'Cannot release ticket with status {self.status}')

        self.status = TicketStatus.AVAILABLE
        self.buyer_id = None
        self.reserved_at = None

    @Logger.io
    def cancel_reservation(self, *, buyer_id: int) -> None:
        if self.status != TicketStatus.RESERVED:
            raise ValueError(f'Cannot cancel reservation for ticket with status {self.status}')

        if self.buyer_id != buyer_id:
            raise ValueError('Cannot cancel reservation that belongs to another buyer')

        self.release()


def _validate_non_empty_string(instance, attribute, value):
    if not value or not value.strip():
        raise ValueError(f'Event {attribute.name} cannot be empty')


@attrs.define
class Event:
    name: str = attrs.field(validator=_validate_non_empty_string)
    description: str = attrs.field(validator=_validate_non_empty_string)
    seller_id: int
    venue_name: str = attrs.field(validator=_validate_non_empty_string)
    seating_config: Dict
    is_active: bool = True
    status: EventStatus = EventStatus.AVAILABLE
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@attrs.define
class EventTicketingAggregate:
    # Event entity
    event: Event

    # Tickets collection - entities within aggregate
    tickets: List[Ticket] = attrs.field(factory=list)

    @classmethod
    @Logger.io
    def create_event_with_tickets(
        cls,
        *,
        name: str,
        description: str,
        seller_id: int,
        venue_name: str,
        seating_config: Dict,
        is_active: bool = True,
    ) -> 'EventTicketingAggregate':
        """
        Create event with tickets - Aggregate root factory method

        This is the only correct way to create EventTicketingAggregate.
        Ensures event and tickets are created together, maintaining aggregate consistency.
        """

        # Validate seating configuration
        cls._validate_seating_config(seating_config)
        event = Event(
            name=name,
            description=description,
            seller_id=seller_id,
            venue_name=venue_name,
            seating_config=seating_config,
            is_active=is_active,
            status=EventStatus.DRAFT,  # Initial status is DRAFT, changes to AVAILABLE after tickets are created
            created_at=datetime.now(timezone.utc),
        )

        # Create aggregate root
        aggregate = cls(event=event, tickets=[])

        return aggregate

    @Logger.io
    def generate_tickets(self) -> List[tuple]:
        """
        Generate tickets based on seating configuration

        Must be called after event is persisted (requires event.id)

        Returns:
            ticket_tuples: Ticket data format suitable for batch insert
                [(event_id, section, subsection, row, seat, price, status), ...]
        """
        if not self.event.id:
            raise ValueError('Event must be persisted before generating tickets')

        if self.tickets:
            raise ValueError('Tickets already generated for this event')

        self.tickets = self._generate_tickets_from_seating_config()
        Logger.base.info(f'Generated {len(self.tickets)} tickets for event {self.event.id}')

        # Also return batch insert format
        ticket_tuples = [
            (
                ticket.event_id,
                ticket.section,
                ticket.subsection,
                ticket.row,
                ticket.seat,
                ticket.price,
                ticket.status.value,
            )
            for ticket in self.tickets
        ]

        return ticket_tuples

    def _generate_tickets_from_seating_config(self) -> List[Ticket]:
        if not self.event.id:
            raise ValueError('Event must have an ID before generating tickets')

        tickets = []
        sections = self.event.seating_config.get('sections', [])

        for section in sections:
            section_name = section['name']
            section_price = int(section['price'])
            subsections = section['subsections']

            for subsection in subsections:
                subsection_number = subsection['number']
                rows = subsection['rows']
                seats_per_row = subsection['seats_per_row']

                for row in range(1, rows + 1):
                    for seat in range(1, seats_per_row + 1):
                        ticket = Ticket(
                            event_id=self.event.id,
                            section=section_name,
                            subsection=subsection_number,
                            row=row,
                            seat=seat,
                            price=section_price,
                            status=TicketStatus.AVAILABLE,
                        )
                        tickets.append(ticket)

        return tickets

    @staticmethod
    def _validate_seating_config(seating_config: Dict) -> None:
        if not isinstance(seating_config, dict) or 'sections' not in seating_config:
            raise ValueError('Invalid seating configuration: must contain sections')

        sections = seating_config.get('sections', [])
        if not isinstance(sections, list) or len(sections) == 0:
            raise ValueError('Invalid seating configuration: sections must be a non-empty list')

        for section in sections:
            if not isinstance(section, dict):
                raise ValueError('Invalid seating configuration: each section must be a dictionary')

            # Check required fields
            required_fields = ['name', 'price', 'subsections']
            for field in required_fields:
                if field not in section:
                    raise ValueError(
                        f'Invalid seating configuration: section missing required field "{field}"'
                    )

            # Validate price
            price = section.get('price')
            if not isinstance(price, (int, float)) or price < 0:
                raise ValueError('Ticket price must over 0')

            # Validate subsections
            subsections = section.get('subsections', [])
            if not isinstance(subsections, list) or len(subsections) == 0:
                raise ValueError(
                    'Invalid seating configuration: each section must have subsections'
                )

            for subsection in subsections:
                if not isinstance(subsection, dict):
                    raise ValueError(
                        'Invalid seating configuration: each subsection must be a dictionary'
                    )

                required_subsection_fields = ['number', 'rows', 'seats_per_row']
                for field in required_subsection_fields:
                    if field not in subsection:
                        raise ValueError(
                            f'Invalid seating configuration: subsection missing required field "{field}"'
                        )

                # Validate numeric fields
                for field in ['number', 'rows', 'seats_per_row']:
                    value = subsection.get(field)
                    if not isinstance(value, int) or value <= 0:
                        raise ValueError(
                            f'Invalid seating configuration: {field} must be a positive integer'
                        )

    @Logger.io
    def reserve_tickets(self, *, ticket_ids: List[int], buyer_id: int) -> List[Ticket]:
        """
        Reserve tickets - Aggregate business logic

        Args:
            ticket_ids: List of ticket IDs to reserve
            buyer_id: Buyer ID

        Returns:
            List of reserved tickets
        """
        reserved_tickets = []

        for ticket_id in ticket_ids:
            ticket = self._find_ticket_by_id(ticket_id)
            if not ticket:
                raise ValueError(f'Ticket {ticket_id} not found in this event')

            # Check ticket status
            if ticket.status != TicketStatus.AVAILABLE:
                raise ValueError(f'Ticket {ticket_id} is not available for reservation')

            # Execute reservation
            ticket.reserve(buyer_id=buyer_id)
            reserved_tickets.append(ticket)

        # Update event status
        self.update_event_status_based_on_tickets()

        return reserved_tickets

    @Logger.io
    def cancel_ticket_reservations(self, *, ticket_ids: List[int], buyer_id: int) -> List[Ticket]:
        """
        Cancel ticket reservations - Aggregate business logic
        """
        cancelled_tickets = []

        for ticket_id in ticket_ids:
            ticket = self._find_ticket_by_id(ticket_id)
            if not ticket:
                raise ValueError(f'Ticket {ticket_id} not found in this event')

            # Check ticket status and ownership
            if ticket.buyer_id != buyer_id:
                raise ValueError(f'Ticket {ticket_id} does not belong to buyer {buyer_id}')

            # Execute cancellation
            ticket.cancel_reservation(buyer_id=buyer_id)
            cancelled_tickets.append(ticket)

        # Update event status
        self.update_event_status_based_on_tickets()

        return cancelled_tickets

    @Logger.io
    def finalize_tickets_as_sold(self, *, ticket_ids: List[int]) -> List[Ticket]:
        """
        Mark tickets as sold
        """
        sold_tickets = []

        for ticket_id in ticket_ids:
            ticket = self._find_ticket_by_id(ticket_id)
            if not ticket:
                raise ValueError(f'Ticket {ticket_id} not found in this event')

            # Execute sale
            ticket.sell()
            sold_tickets.append(ticket)

        # Update event status
        self.update_event_status_based_on_tickets()

        return sold_tickets

    def _find_ticket_by_id(self, ticket_id: int) -> Optional[Ticket]:
        for ticket in self.tickets:
            if ticket.id == ticket_id:
                return ticket
        return None

    def get_tickets_by_section(self, *, section: str, subsection: int) -> List[Ticket]:
        return [
            ticket
            for ticket in self.tickets
            if ticket.section == section and ticket.subsection == subsection
        ]

    def get_available_tickets(self) -> List[Ticket]:
        return [t for t in self.tickets if t.status == TicketStatus.AVAILABLE]

    def get_reserved_tickets(self) -> List[Ticket]:
        return [t for t in self.tickets if t.status == TicketStatus.RESERVED]

    def get_sold_tickets(self) -> List[Ticket]:
        return [t for t in self.tickets if t.status == TicketStatus.SOLD]

    @property
    def total_tickets_count(self) -> int:
        return len(self.tickets)

    @property
    def available_tickets_count(self) -> int:
        return len(self.get_available_tickets())

    @property
    def reserved_tickets_count(self) -> int:
        return len(self.get_reserved_tickets())

    @property
    def sold_tickets_count(self) -> int:
        return len(self.get_sold_tickets())

    @Logger.io
    def update_event_status_based_on_tickets(self) -> None:
        if self.available_tickets_count == 0 and self.total_tickets_count > 0:
            self.event.status = EventStatus.SOLD_OUT
        elif self.total_tickets_count > 0:
            self.event.status = EventStatus.AVAILABLE
        else:
            self.event.status = EventStatus.DRAFT

    @Logger.io
    def activate(self) -> None:
        """
        Activate event - Change from DRAFT to AVAILABLE

        Event can only be activated after all tickets are created.
        Ensures event is only open for purchase after all preparation is complete.
        """
        if self.event.status != EventStatus.DRAFT:
            raise ValueError(
                f'Cannot activate event with status {self.event.status}. Must be DRAFT.'
            )

        if not self.tickets:
            raise ValueError('Cannot activate event without tickets')

        Logger.base.info(f'Activating event {self.event.id} with {len(self.tickets)} tickets')
        self.event.status = EventStatus.AVAILABLE

    def get_statistics(self) -> dict:
        return {
            'event_id': self.event.id,
            'event_name': self.event.name,
            'event_status': self.event.status.value,
            'total_tickets': self.total_tickets_count,
            'available_tickets': self.available_tickets_count,
            'reserved_tickets': self.reserved_tickets_count,
            'sold_tickets': self.sold_tickets_count,
            'total_revenue': sum(t.price for t in self.get_sold_tickets()),
            'potential_revenue': sum(t.price for t in self.tickets),
        }
