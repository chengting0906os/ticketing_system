from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.logging.loguru_io import Logger
from src.ticket.domain.ticket_entity import Ticket, TicketStatus
from src.ticket.domain.ticket_repo import TicketRepo
from src.ticket.infra.ticket_model import TicketModel


class TicketRepoImpl(TicketRepo):
    def __init__(self, session: AsyncSession):
        self.session = session

    @Logger.io
    async def get_by_id(self, *, ticket_id: int) -> Ticket | None:
        result = await self.session.execute(select(TicketModel).where(TicketModel.id == ticket_id))
        db_ticket = result.scalar_one_or_none()
        return self._to_entity(db_ticket) if db_ticket else None

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
            booking_id=db_ticket.booking_id,
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
            booking_id=ticket.booking_id,
            buyer_id=ticket.buyer_id,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            reserved_at=ticket.reserved_at,
        )

    @Logger.io(truncate_content=True)
    async def create_batch(self, *, tickets: List[Ticket]) -> List[Ticket]:
        db_tickets = [self._to_model(ticket) for ticket in tickets]

        self.session.add_all(db_tickets)
        await self.session.flush()

        # Refresh to get IDs and timestamps
        for db_ticket in db_tickets:
            await self.session.refresh(db_ticket)

        return [self._to_entity(db_ticket) for db_ticket in db_tickets]

    @Logger.io
    async def get_by_event_id(self, *, event_id: int) -> List[Ticket]:
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
        self, *, event_id: int, section: str, subsection: int | None = None
    ) -> List[Ticket]:
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
    async def check_tickets_exist_for_event(self, *, event_id: int) -> bool:
        result = await self.session.execute(
            select(TicketModel.id).where(TicketModel.event_id == event_id).limit(1)
        )
        return result.scalar_one_or_none() is not None

    @Logger.io
    async def count_tickets_by_event(self, *, event_id: int) -> int:
        from sqlalchemy import func

        result = await self.session.execute(
            select(func.count(TicketModel.id)).where(TicketModel.event_id == event_id)
        )
        return result.scalar() or 0

    @Logger.io
    async def get_available_tickets_by_event(self, *, event_id: int) -> List[Ticket]:
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

    @Logger.io
    async def get_available_tickets_for_event(
        self, *, event_id: int, limit: int | None = None
    ) -> List[Ticket]:
        query = (
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

        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        db_tickets = result.scalars().all()
        return [self._to_entity(db_ticket) for db_ticket in db_tickets]

    @Logger.io
    async def get_reserved_tickets_for_event(self, *, event_id: int) -> List[Ticket]:
        result = await self.session.execute(
            select(TicketModel)
            .where(TicketModel.event_id == event_id)
            .where(TicketModel.status == TicketStatus.RESERVED.value)
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
    async def get_reserved_tickets_by_buyer(self, *, buyer_id: int) -> List[Ticket]:
        result = await self.session.execute(
            select(TicketModel)
            .where(TicketModel.buyer_id == buyer_id)
            .where(TicketModel.status == TicketStatus.RESERVED.value)
        )
        db_tickets = result.scalars().all()
        return [self._to_entity(db_ticket) for db_ticket in db_tickets]

    @Logger.io
    async def get_reserved_tickets_by_buyer_and_event(
        self, *, buyer_id: int, event_id: int
    ) -> List[Ticket]:
        result = await self.session.execute(
            select(TicketModel)
            .where(TicketModel.buyer_id == buyer_id)
            .where(TicketModel.event_id == event_id)
            .where(TicketModel.status == TicketStatus.RESERVED.value)
        )
        db_tickets = result.scalars().all()
        return [self._to_entity(db_ticket) for db_ticket in db_tickets]

    @Logger.io
    async def get_tickets_by_booking_id(self, *, booking_id: int) -> List[Ticket]:
        result = await self.session.execute(
            select(TicketModel).where(TicketModel.booking_id == booking_id)
        )
        db_tickets = result.scalars().all()
        return [self._to_entity(db_ticket) for db_ticket in db_tickets]

    @Logger.io
    async def get_all_reserved_tickets(self) -> List[Ticket]:
        result = await self.session.execute(
            select(TicketModel).where(TicketModel.status == TicketStatus.RESERVED.value)
        )
        db_tickets = result.scalars().all()
        return [self._to_entity(db_ticket) for db_ticket in db_tickets]

    @Logger.io
    async def update_batch(self, *, tickets: List[Ticket]) -> List[Ticket]:
        for ticket in tickets:
            # Find the existing model
            result = await self.session.execute(
                select(TicketModel).where(TicketModel.id == ticket.id)
            )
            db_ticket = result.scalar_one()

            # Update the fields
            db_ticket.status = ticket.status.value
            db_ticket.buyer_id = ticket.buyer_id
            db_ticket.booking_id = ticket.booking_id
            db_ticket.reserved_at = ticket.reserved_at
            if ticket.updated_at is not None:
                db_ticket.updated_at = ticket.updated_at

        await self.session.flush()

        # Return updated entities
        updated_tickets = []
        for ticket in tickets:
            result = await self.session.execute(
                select(TicketModel).where(TicketModel.id == ticket.id)
            )
            db_ticket = result.scalar_one()
            updated_tickets.append(self._to_entity(db_ticket))

        return updated_tickets
