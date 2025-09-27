from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from src.event_ticketing.domain.ticket_command_repo import TicketCommandRepo
from src.event_ticketing.domain.ticket_entity import Ticket, TicketStatus
from src.event_ticketing.infra.ticket_model import TicketModel
from src.shared.logging.loguru_io import Logger


class TicketCommandRepoImpl(TicketCommandRepo):
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_entity(db_ticket: TicketModel) -> Ticket:
        return Ticket(
            id=db_ticket.id,
            event_id=db_ticket.event_id,
            section=db_ticket.section,
            subsection=db_ticket.subsection,
            row=db_ticket.row_number,
            seat=db_ticket.seat_number,
            price=db_ticket.price,
            status=TicketStatus(db_ticket.status),
            buyer_id=db_ticket.buyer_id,
            created_at=db_ticket.created_at,
            updated_at=db_ticket.updated_at,
            reserved_at=db_ticket.reserved_at,
        )

    @staticmethod
    def _to_model(ticket: Ticket) -> TicketModel:
        return TicketModel(
            id=ticket.id,
            event_id=ticket.event_id,
            section=ticket.section,
            subsection=ticket.subsection,
            row_number=ticket.row,
            seat_number=ticket.seat,
            price=ticket.price,
            status=ticket.status.value,
            buyer_id=ticket.buyer_id,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            reserved_at=ticket.reserved_at,
        )

    @Logger.io
    async def create_batch(self, *, tickets: List[Ticket]) -> List[Ticket]:
        db_tickets = [self._to_model(ticket) for ticket in tickets]

        self.session.add_all(db_tickets)
        await self.session.flush()

        for db_ticket in db_tickets:
            await self.session.refresh(db_ticket)

        return [self._to_entity(db_ticket) for db_ticket in db_tickets]

    @Logger.io
    async def update_batch(self, *, tickets: List[Ticket]) -> List[Ticket]:
        updated_tickets = []

        for ticket in tickets:
            db_ticket = await self.session.get(TicketModel, ticket.id)
            if db_ticket:
                db_ticket.status = ticket.status.value
                db_ticket.buyer_id = ticket.buyer_id
                db_ticket.reserved_at = ticket.reserved_at
                if ticket.updated_at is not None:
                    db_ticket.updated_at = ticket.updated_at

                await self.session.flush()
                await self.session.refresh(db_ticket)
                updated_tickets.append(self._to_entity(db_ticket))

        return updated_tickets
