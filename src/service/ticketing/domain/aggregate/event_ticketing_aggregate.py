"""
Event Ticketing Aggregate - Aggregate Root for Event Ticketing

[DDD Design Principles]
- EventTicketingAggregate is the Aggregate Root
- Event and Ticket are entities within the aggregate
- Ensures transactional consistency for event and ticket creation

[Business Invariants]
- Event must have valid seating configuration
- Ticket count must match seating configuration
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

import attrs

from src.platform.logging.loguru_io import Logger
from src.service.ticketing.domain.entity.subsection_stats_entity import SubsectionStatsEntity
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


def _validate_non_empty_string(instance: object, attribute: attrs.Attribute, value: str) -> None:
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
    stats: Optional[Dict] = None


@attrs.define
class EventTicketingAggregate:
    # Event entity
    event: Event

    # Tickets collection - entities within aggregate
    tickets: List[Ticket] = attrs.field(factory=list)

    # Subsection stats - read from subsection_stats table
    subsection_stats: List[SubsectionStatsEntity] = attrs.field(factory=list)

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
        """Generate tickets from seating config (compact format only)."""
        if not self.event.id:
            raise ValueError('Event must have an ID before generating tickets')

        tickets = []
        config = self.event.seating_config

        rows = config.get('rows', 1)
        cols = config.get('cols', 10)

        for section in config.get('sections', []):
            section_name = section['name']
            section_price = int(section['price'])
            subsection_count = section['subsections']

            for subsection_num in range(1, subsection_count + 1):
                for row in range(1, rows + 1):
                    for seat in range(1, cols + 1):
                        ticket = Ticket(
                            event_id=self.event.id,
                            section=section_name,
                            subsection=subsection_num,
                            row=row,
                            seat=seat,
                            price=section_price,
                            status=TicketStatus.AVAILABLE,
                        )
                        tickets.append(ticket)

        return tickets

    @staticmethod
    def _validate_seating_config(seating_config: Dict) -> None:
        """Validate seating config (compact format only)."""
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

            # Validate subsections (compact format: must be positive int)
            subsections = section.get('subsections')
            if not isinstance(subsections, int) or subsections <= 0:
                raise ValueError(
                    'Invalid seating configuration: subsections must be a positive integer'
                )

    @property
    def total_tickets_count(self) -> int:
        return len(self.tickets)


@attrs.define
class SubsectionTicketsAggregate:
    """Aggregate for subsection stats with tickets."""

    stats: SubsectionStatsEntity
    tickets: List[Ticket] = attrs.field(factory=list)
