"""Ticket repository implementation."""

from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ticket.domain.ticket_entity import Ticket, TicketStatus
from src.ticket.domain.ticket_repo import TicketRepo
from src.ticket.infra.ticket_model import TicketModel
from src.shared.logging.loguru_io import Logger


class TicketRepoImpl(TicketRepo):
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
            order_id=db_ticket.order_id,
            buyer_id=db_ticket.buyer_id,
            created_at=db_ticket.created_at,
            updated_at=db_ticket.updated_at,
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
            order_id=ticket.order_id,
            buyer_id=ticket.buyer_id,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
        )

    @Logger.io
    async def create_batch(self, tickets: List[Ticket]) -> List[Ticket]:
        """Create multiple tickets in batch."""
        db_tickets = [self._to_model(ticket) for ticket in tickets]

        self.session.add_all(db_tickets)
        await self.session.flush()

        # Refresh to get IDs and timestamps
        for db_ticket in db_tickets:
            await self.session.refresh(db_ticket)

        return [self._to_entity(db_ticket) for db_ticket in db_tickets]

    @Logger.io
    async def get_by_event_id(self, event_id: int) -> List[Ticket]:
        """Get all tickets for an event."""
        result = await self.session.execute(
            select(TicketModel)
            .where(TicketModel.event_id == event_id)
            .order_by(
                TicketModel.section,
                TicketModel.subsection,
                TicketModel.row_number,
                TicketModel.seat_number,
            )
        )
        db_tickets = result.scalars().all()
        return [self._to_entity(db_ticket) for db_ticket in db_tickets]

    @Logger.io
    async def get_by_event_and_section(
        self, event_id: int, section: str, subsection: int | None = None
    ) -> List[Ticket]:
        """Get tickets for specific section/subsection of an event."""
        query = (
            select(TicketModel)
            .where(TicketModel.event_id == event_id)
            .where(TicketModel.section == section)
        )

        if subsection is not None:
            query = query.where(TicketModel.subsection == subsection)

        result = await self.session.execute(
            query.order_by(TicketModel.subsection, TicketModel.row_number, TicketModel.seat_number)
        )
        db_tickets = result.scalars().all()
        return [self._to_entity(db_ticket) for db_ticket in db_tickets]

    @Logger.io
    async def check_tickets_exist_for_event(self, event_id: int) -> bool:
        """Check if any tickets exist for an event."""
        result = await self.session.execute(
            select(TicketModel.id).where(TicketModel.event_id == event_id).limit(1)
        )
        return result.scalar_one_or_none() is not None

    @Logger.io
    async def count_tickets_by_event(self, event_id: int) -> int:
        """Count total tickets for an event."""
        from sqlalchemy import func

        result = await self.session.execute(
            select(func.count(TicketModel.id)).where(TicketModel.event_id == event_id)
        )
        return result.scalar() or 0

    @Logger.io
    async def get_available_tickets_by_event(self, event_id: int) -> List[Ticket]:
        """Get all available tickets for an event."""
        result = await self.session.execute(
            select(TicketModel)
            .where(TicketModel.event_id == event_id)
            .where(TicketModel.status == TicketStatus.AVAILABLE.value)
            .order_by(
                TicketModel.section,
                TicketModel.subsection,
                TicketModel.row_number,
                TicketModel.seat_number,
            )
        )
        db_tickets = result.scalars().all()
        return [self._to_entity(db_ticket) for db_ticket in db_tickets]
