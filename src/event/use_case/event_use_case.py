from typing import Dict, List, Optional

from fastapi import Depends

from src.event.domain.event_entity import Event
from src.shared.logging.loguru_io import Logger
from src.shared.service.unit_of_work import AbstractUnitOfWork, get_unit_of_work
from src.ticket.domain.ticket_entity import Ticket, TicketStatus


class CreateEventUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow)

    @Logger.io
    async def create(
        self,
        name: str,
        description: str,
        seller_id: int,
        venue_name: str,
        seating_config: Dict,
        is_active: bool = True,
    ) -> Event:
        async with self.uow:
            # Validate seating config and prices
            self._validate_seating_config(seating_config)

            event = Event.create(
                name=name,
                description=description,
                seller_id=seller_id,
                venue_name=venue_name,
                seating_config=seating_config,
                is_active=is_active,
            )

            created_event = await self.uow.events.create(event=event)

            # Auto-create tickets based on seating configuration
            if created_event.id is not None:
                tickets = self._generate_tickets_from_seating_config(
                    event_id=created_event.id, seating_config=seating_config
                )
                await self.uow.tickets.create_batch(tickets=tickets)

            await self.uow.commit()
        # raise Exception('Simulated error for testing rollback')  # --- IGNORE ---
        return created_event

    def _validate_seating_config(self, seating_config: Dict) -> None:
        """Validate seating configuration structure and prices."""
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
            if not isinstance(price, (int, float)) or price <= 0:
                raise ValueError('Ticket price must be positive')

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
        self, event_id: int, seating_config: Dict
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
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow)

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
        async with self.uow:
            # Get existing event
            event = await self.uow.events.get_by_id(event_id=event_id)
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

            updated_event = await self.uow.events.update(event=event)
            await self.uow.commit()

        return updated_event


class GetEventUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow)

    @Logger.io
    async def get_by_id(self, event_id: int) -> Optional[Event]:
        async with self.uow:
            event = await self.uow.events.get_by_id(event_id=event_id)
        return event


class ListEventsUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow)

    @Logger.io
    async def get_by_seller(self, seller_id: int) -> List[Event]:
        async with self.uow:
            events = await self.uow.events.get_by_seller(seller_id=seller_id)
        return events

    @Logger.io
    async def list_available(self) -> List[Event]:
        async with self.uow:
            events = await self.uow.events.list_available()
        return events
