from typing import List

from fastapi import Depends

from src.shared.exception.exceptions import ForbiddenError, NotFoundError
from src.shared.logging.loguru_io import Logger
from src.shared.service.unit_of_work import AbstractUnitOfWork, get_unit_of_work
from src.event.domain.ticket_entity import Ticket


class ListTicketsUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @Logger.io
    async def list_tickets_by_event(
        self, *, event_id: int, seller_id: int | None = None
    ) -> List[Ticket]:
        async with self.uow:
            # Verify event exists
            event = await self.uow.events.get_by_id(event_id=event_id)
            if not event:
                raise NotFoundError('Event not found')

            # If seller_id provided, verify they own the event and return all tickets
            if seller_id is not None:
                if event.seller_id != seller_id:
                    raise ForbiddenError('Not authorized to view tickets for this event')
                tickets = await self.uow.tickets.get_by_event_id(event_id=event_id)
            else:
                # For buyers, return only available tickets
                tickets = await self.uow.tickets.get_available_tickets_by_event(event_id=event_id)

            return tickets

    @Logger.io
    async def list_tickets_by_section(
        self, *, event_id: int, section: str, subsection: int | None, seller_id: int
    ) -> List[Ticket]:
        async with self.uow:
            # Verify seller owns the event
            event = await self.uow.events.get_by_id(event_id=event_id)
            if not event:
                raise NotFoundError('Event not found')

            if event.seller_id != seller_id:
                raise ForbiddenError('Not authorized to view tickets for this event')

            tickets = await self.uow.tickets.get_by_event_and_section(
                event_id=event_id, section=section, subsection=subsection
            )
            return tickets

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow=uow)
