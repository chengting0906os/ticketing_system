from typing import List

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.event_ticketing.domain.ticket_entity import Ticket, TicketStatus
from src.event_ticketing.domain.ticket_query_repo import TicketQueryRepo
from src.event_ticketing.infra.ticket_model import TicketModel
from src.shared.logging.loguru_io import Logger


class TicketQueryRepoImpl(TicketQueryRepo):
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

    @Logger.io
    async def get_by_id(self, *, ticket_id: int) -> Ticket | None:
        result = await self.session.execute(select(TicketModel).where(TicketModel.id == ticket_id))
        db_ticket = result.scalar_one_or_none()
        return self._to_entity(db_ticket) if db_ticket else None

    @Logger.io(truncate_content=True)
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

    @Logger.io(truncate_content=True)
    async def list_by_event_section_and_subsection(
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
            .where(TicketModel.buyer_id.is_(None))
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
    async def get_available_tickets_for_section(
        self, *, event_id: int, section: str, subsection: int, limit: int | None = None
    ) -> List[Ticket]:
        query = (
            select(TicketModel)
            .where(TicketModel.event_id == event_id)
            .where(TicketModel.status == TicketStatus.AVAILABLE.value)
        )

        if section:
            query = query.where(TicketModel.section == section)

        if subsection:
            query = query.where(TicketModel.subsection == subsection)

        query = query.order_by(
            TicketModel.section,
            TicketModel.subsection,
            TicketModel.row_number,
            TicketModel.seat_number,
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
    async def get_all_reserved_tickets(self) -> List[Ticket]:
        result = await self.session.execute(
            select(TicketModel).where(TicketModel.status == TicketStatus.RESERVED.value)
        )
        db_tickets = result.scalars().all()
        return [self._to_entity(db_ticket) for db_ticket in db_tickets]

    @Logger.io
    async def get_all_available(self) -> List[Ticket]:
        result = await self.session.execute(
            select(TicketModel).where(TicketModel.status == TicketStatus.AVAILABLE.value)
        )
        db_tickets = result.scalars().all()
        return [self._to_entity(db_ticket) for db_ticket in db_tickets]

    @Logger.io
    async def get_by_seat_location(
        self, *, section: str, subsection: int, row_number: int, seat_number: int
    ) -> Ticket | None:
        result = await self.session.execute(
            select(TicketModel)
            .where(TicketModel.section == section)
            .where(TicketModel.subsection == subsection)
            .where(TicketModel.row_number == row_number)
            .where(TicketModel.seat_number == seat_number)
        )
        db_ticket = result.scalar_one_or_none()
        return self._to_entity(db_ticket) if db_ticket else None

    @Logger.io
    async def get_available_tickets_limit(self, *, limit: int) -> List[Ticket]:
        result = await self.session.execute(
            select(TicketModel)
            .where(TicketModel.status == TicketStatus.AVAILABLE.value)
            .order_by(
                TicketModel.section,
                TicketModel.subsection,
                TicketModel.row_number,
                TicketModel.seat_number,
            )
            .limit(limit)
        )
        db_tickets = result.scalars().all()
        return [self._to_entity(db_ticket) for db_ticket in db_tickets]

    @Logger.io
    async def get_ticket_stats_by_event(self, *, event_id: int) -> dict:
        """Returns ticket statistics for an event."""
        result = await self.session.execute(
            select(
                func.count(TicketModel.id).label('total'),
                func.sum(
                    case((TicketModel.status == TicketStatus.AVAILABLE.value, 1), else_=0)
                ).label('available'),
                func.sum(
                    case((TicketModel.status == TicketStatus.RESERVED.value, 1), else_=0)
                ).label('reserved'),
                func.sum(case((TicketModel.status == TicketStatus.SOLD.value, 1), else_=0)).label(
                    'sold'
                ),
            ).where(TicketModel.event_id == event_id)
        )
        stats = result.first()

        return {
            'total': stats.total or 0,  # pyright: ignore[reportOptionalMemberAccess]
            'available': stats.available or 0,  # pyright: ignore[reportOptionalMemberAccess]
            'reserved': stats.reserved or 0,  # pyright: ignore[reportOptionalMemberAccess]
            'sold': stats.sold or 0,  # pyright: ignore[reportOptionalMemberAccess]
        }

    @Logger.io
    async def get_ticket_stats_by_section(
        self, *, event_id: int, section: str, subsection: int | None = None
    ) -> dict:
        """Returns ticket statistics for a section/subsection."""
        query = select(
            func.count(TicketModel.id).label('total'),
            func.sum(case((TicketModel.status == TicketStatus.AVAILABLE.value, 1), else_=0)).label(
                'available'
            ),
            func.sum(case((TicketModel.status == TicketStatus.RESERVED.value, 1), else_=0)).label(
                'reserved'
            ),
            func.sum(case((TicketModel.status == TicketStatus.SOLD.value, 1), else_=0)).label(
                'sold'
            ),
        ).where(TicketModel.event_id == event_id, TicketModel.section == section)

        if subsection is not None:
            query = query.where(TicketModel.subsection == subsection)

        result = await self.session.execute(query)
        stats = result.first()

        return {
            'total': stats.total or 0,  # pyright: ignore[reportOptionalMemberAccess]
            'available': stats.available or 0,  # pyright: ignore[reportOptionalMemberAccess]
            'reserved': stats.reserved or 0,  # pyright: ignore[reportOptionalMemberAccess]
            'sold': stats.sold or 0,  # pyright: ignore[reportOptionalMemberAccess]
        }

    @Logger.io
    async def get_sections_with_stats(self, *, event_id: int) -> List[dict]:
        """Returns all sections with their subsection statistics."""
        result = await self.session.execute(
            select(
                TicketModel.section,
                TicketModel.subsection,
                func.count(TicketModel.id).label('total'),
                func.sum(
                    case((TicketModel.status == TicketStatus.AVAILABLE.value, 1), else_=0)
                ).label('available'),
                func.sum(
                    case((TicketModel.status == TicketStatus.RESERVED.value, 1), else_=0)
                ).label('reserved'),
                func.sum(case((TicketModel.status == TicketStatus.SOLD.value, 1), else_=0)).label(
                    'sold'
                ),
            )
            .where(TicketModel.event_id == event_id)
            .group_by(TicketModel.section, TicketModel.subsection)
            .order_by(TicketModel.section, TicketModel.subsection)
        )

        rows = result.all()

        sections_dict = {}
        for row in rows:
            section = row.section
            if section not in sections_dict:
                sections_dict[section] = {'section': section, 'subsections': []}

            sections_dict[section]['subsections'].append(
                {
                    'subsection': row.subsection,
                    'total': row.total or 0,
                    'available': row.available or 0,
                    'reserved': row.reserved or 0,
                    'sold': row.sold or 0,
                }
            )

        return list(sections_dict.values())
