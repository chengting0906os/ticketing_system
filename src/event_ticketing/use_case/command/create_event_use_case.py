from typing import Dict, List, Optional

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.event_ticketing.domain.event_entity import Event
from src.event_ticketing.domain.event_command_repo import EventCommandRepo
from src.event_ticketing.domain.event_query_repo import EventQueryRepo
from src.event_ticketing.domain.ticket_entity import Ticket, TicketStatus
from src.event_ticketing.domain.ticket_repo import TicketRepo
from src.shared.logging.loguru_io import Logger
from src.shared.config.db_setting import get_async_session


class CreateEventUseCase:
    def __init__(self, event_repo: EventCommandRepo, ticket_repo: TicketRepo):
        self.event_repo = event_repo
        self.ticket_repo = ticket_repo

    @classmethod
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
    ):
        from src.event_ticketing.infra.event_command_repo_impl import EventCommandRepoImpl
        from src.event_ticketing.infra.ticket_repo_impl import TicketRepoImpl

        event_repo = EventCommandRepoImpl(session)
        ticket_repo = TicketRepoImpl(session)
        return cls(event_repo=event_repo, ticket_repo=ticket_repo)

    @Logger.io
    async def create(
        self,
        *,
        name: str,
        description: str,
        seller_id: int,
        venue_name: str,
        seating_config: Dict,
        is_active: bool = True,
    ) -> Event:
        # Validate seating config and prices
        self._validate_seating_config(seating_config=seating_config)

        event = Event.create(
            name=name,
            description=description,
            seller_id=seller_id,
            venue_name=venue_name,
            seating_config=seating_config,
            is_active=is_active,
        )

        created_event = await self.event_repo.create(event=event)

        # Auto-create tickets based on seating configuration
        if created_event.id is not None:
            tickets = self._generate_tickets_from_seating_config(
                event_id=created_event.id, seating_config=seating_config
            )
            await self.ticket_repo.create_batch(tickets=tickets)

        return created_event

    def _validate_seating_config(self, *, seating_config: Dict) -> None:
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

    def _generate_tickets_from_seating_config(
        self, *, event_id: int, seating_config: Dict
    ) -> List[Ticket]:
        """Generate tickets based on seating configuration."""
        tickets = []
        sections = seating_config.get('sections', [])

        for section in sections:
            section_name = section['name']
            section_price = int(section['price'])
            subsections = section['subsections']

            for subsection in subsections:
                subsection_number = subsection['number']
                rows = subsection['rows']
                seats_per_row = subsection['seats_per_row']

                # Generate tickets for each seat
                for row in range(1, rows + 1):
                    for seat in range(1, seats_per_row + 1):
                        ticket = Ticket(
                            event_id=event_id,
                            section=section_name,
                            subsection=subsection_number,
                            row=row,
                            seat=seat,
                            price=section_price,
                            status=TicketStatus.AVAILABLE,
                        )
                        tickets.append(ticket)

        return tickets


class UpdateEventUseCase:
    def __init__(self, event_command_repo: EventCommandRepo, event_query_repo: EventQueryRepo):
        self.event_command_repo = event_command_repo
        self.event_query_repo = event_query_repo

    @classmethod
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
    ):
        from src.event_ticketing.infra.event_command_repo_impl import EventCommandRepoImpl
        from src.event_ticketing.infra.event_query_repo_impl import EventQueryRepoImpl

        event_command_repo = EventCommandRepoImpl(session)
        event_query_repo = EventQueryRepoImpl(session)
        return cls(event_command_repo=event_command_repo, event_query_repo=event_query_repo)

    @Logger.io
    async def update(
        self,
        event_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        venue_name: Optional[str] = None,
        seating_config: Optional[Dict] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[Event]:
        # Get existing event
        event = await self.event_query_repo.get_by_id(event_id=event_id)
        if not event:
            return None

        # Update only provided fields
        if name is not None:
            event.name = name
        if description is not None:
            event.description = description
        if venue_name is not None:
            event.venue_name = venue_name
        if seating_config is not None:
            event.seating_config = seating_config
        if is_active is not None:
            event.is_active = is_active

        updated_event = await self.event_command_repo.update(event=event)
        return updated_event
