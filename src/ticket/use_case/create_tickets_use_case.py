"""Create tickets use case."""

from typing import List

from fastapi import Depends

from src.shared.exception.exceptions import ForbiddenError, NotFoundError, DomainError
from src.shared.logging.loguru_io import Logger
from src.shared.service.unit_of_work import AbstractUnitOfWork, get_unit_of_work
from src.ticket.domain.ticket_entity import Ticket, TicketStatus


class CreateTicketsUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow=uow)

    @Logger.io
    async def create_all_tickets_for_event(
        self, event_id: int, price: int, seller_id: int
    ) -> List[Ticket]:
        """Create all tickets for an event based on seating configuration."""

        async with self.uow:
            # Get event and verify ownership
            event = await self.uow.events.get_by_id(event_id)
            if not event:
                raise NotFoundError('Event not found')

            if event.seller_id != seller_id:
                raise ForbiddenError('Not authorized to create tickets for this event')

            # Check if tickets already exist
            tickets_exist = await self.uow.tickets.check_tickets_exist_for_event(event_id)
            if tickets_exist:
                raise DomainError('Tickets already exist for this event')

            # Parse seating configuration
            seating_config = event.seating_config
            tickets_to_create = self._generate_tickets_from_config(event_id, price, seating_config)

            # Create tickets in batch
            created_tickets = await self.uow.tickets.create_batch(tickets_to_create)
            await self.uow.commit()

            return created_tickets

    def _generate_tickets_from_config(
        self, event_id: int, price: int, seating_config: dict
    ) -> List[Ticket]:
        """Generate ticket entities from seating configuration."""
        tickets = []

        # Handle both formats: legacy and new nested format
        if 'sections' in seating_config and isinstance(seating_config['sections'], list):
            # Check if it's the new nested format
            if seating_config['sections'] and isinstance(seating_config['sections'][0], dict):
                # New nested format: {"sections": [{"section": "A", "subsections": [{"subsection": 1, "rows": 5, "seats_per_row": 10}]}]}
                for section_config in seating_config['sections']:
                    section_name = section_config.get('section')
                    for subsection_config in section_config.get('subsections', []):
                        subsection = subsection_config.get('subsection')
                        rows = subsection_config.get('rows', 20)
                        seats_per_row = subsection_config.get('seats_per_row', 25)

                        for row in range(1, rows + 1):
                            for seat in range(1, seats_per_row + 1):
                                ticket = Ticket(
                                    event_id=event_id,
                                    section=section_name,
                                    subsection=subsection,
                                    row=row,
                                    seat=seat,
                                    price=price,
                                    status=TicketStatus.AVAILABLE,
                                )
                                tickets.append(ticket)
                return tickets
            else:
                # Legacy format: {"sections": ["A","B",...], "subsections": [1,2,...], ...}
                sections = seating_config.get('sections', [])
                subsections = seating_config.get('subsections', [])
                rows_per_subsection = seating_config.get('rows_per_subsection', 20)
                seats_per_row = seating_config.get('seats_per_row', 25)
        else:
            # Fallback to empty
            sections = []
            subsections = []
            rows_per_subsection = 20
            seats_per_row = 25

        for section in sections:
            for subsection in subsections:
                for row in range(1, rows_per_subsection + 1):
                    for seat in range(1, seats_per_row + 1):
                        ticket = Ticket(
                            event_id=event_id,
                            section=section,
                            subsection=subsection,
                            row=row,
                            seat=seat,
                            price=price,
                            status=TicketStatus.AVAILABLE,
                        )
                        tickets.append(ticket)

        return tickets
