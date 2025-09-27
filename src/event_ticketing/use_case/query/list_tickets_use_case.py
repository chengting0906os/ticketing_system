from typing import List

from fastapi import Depends

from src.event_ticketing.domain.event_query_repo import EventQueryRepo
from src.event_ticketing.domain.ticket_entity import Ticket
from src.event_ticketing.domain.ticket_repo import TicketRepo
from src.shared.exception.exceptions import ForbiddenError, NotFoundError
from src.shared.logging.loguru_io import Logger
from src.shared.service.repo_di import get_event_query_repo, get_ticket_repo


class ListTicketsUseCase:
    def __init__(self, event_repo: EventQueryRepo, ticket_repo: TicketRepo):
        self.event_repo = event_repo
        self.ticket_repo = ticket_repo

    @Logger.io(truncate_content=True)
    async def list_tickets_by_event(
        self, *, event_id: int, seller_id: int | None = None
    ) -> List[Ticket]:
        # Verify event exists
        event = await self.event_repo.get_by_id(event_id=event_id)
        if not event:
            raise NotFoundError('Event not found')

        # If seller_id provided, verify they own the event and return all tickets
        if seller_id is not None:
            if event.seller_id != seller_id:
                raise ForbiddenError('Not authorized to view tickets for this event')
            tickets = await self.ticket_repo.get_by_event_id(event_id=event_id)
        else:
            # For buyers, return only available tickets
            tickets = await self.ticket_repo.get_available_tickets_by_event(event_id=event_id)

        return tickets

    @Logger.io(truncate_content=True)
    async def list_tickets_by_event_section_section(
        self, *, event_id: int, section: str, subsection: int
    ) -> List[Ticket]:
        # Verify seller owns the event
        event = await self.event_repo.get_by_id(event_id=event_id)
        if not event:
            raise NotFoundError('Event not found')

        tickets = await self.ticket_repo.list_by_event_section_and_subsection(
            event_id=event_id, section=section, subsection=subsection
        )
        return tickets

    @classmethod
    def depends(
        cls,
        event_repo: EventQueryRepo = Depends(get_event_query_repo),
        ticket_repo: TicketRepo = Depends(get_ticket_repo),
    ):
        return cls(event_repo=event_repo, ticket_repo=ticket_repo)
