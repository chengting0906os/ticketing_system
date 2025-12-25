"""
Event Ticketing Query Repository Implementation - CQRS Read Side
"""

from contextlib import asynccontextmanager
from typing import AsyncContextManager, AsyncIterator, Callable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_event_ticketing_query_repo import (
    IEventTicketingQueryRepo,
)
from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import (
    EventTicketingAggregate,
    SubsectionTicketsAggregate,
)
from src.service.ticketing.domain.entity.event_entity import EventEntity
from src.service.ticketing.domain.entity.subsection_stats_entity import SubsectionStatsEntity
from src.service.ticketing.domain.entity.ticket_entity import TicketEntity
from src.service.ticketing.domain.enum.event_status import EventStatus
from src.service.ticketing.domain.enum.ticket_status import TicketStatus
from src.service.ticketing.driven_adapter.model.event_model import EventModel
from src.service.ticketing.driven_adapter.model.subsection_stat_model import SubsectionStatModel
from src.service.ticketing.driven_adapter.model.ticket_model import TicketModel


class EventTicketingQueryRepoImpl(IEventTicketingQueryRepo):
    """Event Ticketing Query Repository Implementation - CQRS Read Side"""

    def __init__(
        self, session_factory: Callable[..., AsyncContextManager[AsyncSession]] | None = None
    ) -> None:
        self.session_factory = session_factory
        self.session: AsyncSession | None = None

    @asynccontextmanager
    async def _get_session(self) -> AsyncIterator[AsyncSession]:
        if self.session is not None:
            yield self.session
        elif self.session_factory is not None:
            async with self.session_factory() as session:
                yield session
        else:
            raise RuntimeError('No session or session_factory available')

    def _model_to_event(self, event_model: EventModel) -> EventEntity:
        return EventEntity(
            name=event_model.name,
            description=event_model.description,
            seller_id=event_model.seller_id,
            venue_name=event_model.venue_name,
            seating_config=event_model.seating_config,
            is_active=event_model.is_active,
            status=EventStatus(event_model.status),
            id=event_model.id,
            created_at=None,
            updated_at=None,
            stats=event_model.stats,
        )

    def _model_to_ticket(self, ticket_model: TicketModel) -> TicketEntity:
        return TicketEntity(
            event_id=ticket_model.event_id,
            section=ticket_model.section,
            subsection=ticket_model.subsection,
            row=ticket_model.row_number,
            seat=ticket_model.seat_number,
            price=ticket_model.price,
            status=TicketStatus(ticket_model.status),
            buyer_id=ticket_model.buyer_id,
            id=ticket_model.id,
            created_at=ticket_model.created_at,
            updated_at=ticket_model.updated_at,
            reserved_at=ticket_model.reserved_at,
        )

    def _model_to_subsection_stats(self, model: SubsectionStatModel) -> SubsectionStatsEntity:
        return SubsectionStatsEntity(
            event_id=model.event_id,
            section=model.section,
            subsection=model.subsection,
            price=model.price,
            available=model.available,
            reserved=model.reserved,
            sold=model.sold,
            updated_at=model.updated_at,
        )

    @Logger.io
    async def get_event_aggregate_by_id_with_tickets(
        self, *, event_id: int
    ) -> Optional[EventTicketingAggregate]:
        async with self._get_session() as session:
            # Query event and tickets
            result = await session.execute(
                select(EventModel, TicketModel)
                .outerjoin(TicketModel, EventModel.id == TicketModel.event_id)
                .where(EventModel.id == event_id)
            )
            rows = result.all()

            if not rows:
                return None

            event_model = rows[0][0]
            event = self._model_to_event(event_model)

            tickets = [
                self._model_to_ticket(ticket_model)
                for _, ticket_model in rows
                if ticket_model is not None
            ]

            # Query subsection stats
            stats_result = await session.execute(
                select(SubsectionStatModel)
                .where(SubsectionStatModel.event_id == event_id)
                .order_by(SubsectionStatModel.section, SubsectionStatModel.subsection)
            )
            stats_models = stats_result.scalars().all()
            subsection_stats = [self._model_to_subsection_stats(m) for m in stats_models]

            aggregate = EventTicketingAggregate(
                event=event, tickets=tickets, subsection_stats=subsection_stats
            )
            Logger.base.info(
                f'[GET_AGGREGATE] Loaded event {event_id} with {len(tickets)} tickets, '
                f'{len(subsection_stats)} subsection stats'
            )
            return aggregate

    @Logger.io
    async def list_events_by_seller(self, *, seller_id: int) -> List[EventTicketingAggregate]:
        async with self._get_session() as session:
            result = await session.execute(
                select(EventModel).where(EventModel.seller_id == seller_id)
            )
            event_models = result.scalars().all()

            aggregates = [
                EventTicketingAggregate(event=self._model_to_event(m), tickets=[])
                for m in event_models
            ]
            Logger.base.info(
                f'[LIST_BY_SELLER] Found {len(aggregates)} events for seller {seller_id}'
            )
            return aggregates

    @Logger.io
    async def list_available_events(self) -> List[EventTicketingAggregate]:
        async with self._get_session() as session:
            result = await session.execute(
                select(EventModel)
                .where(EventModel.is_active)
                .where(EventModel.status == EventStatus.AVAILABLE.value)
            )
            event_models = result.scalars().all()

            aggregates = [
                EventTicketingAggregate(event=self._model_to_event(m), tickets=[])
                for m in event_models
            ]
            Logger.base.info(f'[LIST_AVAILABLE] Found {len(aggregates)} available events')
            return aggregates

    @Logger.io
    async def get_subsection_stats_and_tickets(
        self, *, event_id: int, section: str, subsection: int
    ) -> Optional[SubsectionTicketsAggregate]:
        """Get subsection stats and tickets using ORM with LEFT JOIN."""
        async with self._get_session() as session:
            # Single query with LEFT JOIN
            result = await session.execute(
                select(SubsectionStatModel, TicketModel)
                .outerjoin(
                    TicketModel,
                    (SubsectionStatModel.event_id == TicketModel.event_id)
                    & (SubsectionStatModel.section == TicketModel.section)
                    & (SubsectionStatModel.subsection == TicketModel.subsection),
                )
                .where(SubsectionStatModel.event_id == event_id)
                .where(SubsectionStatModel.section == section)
                .where(SubsectionStatModel.subsection == subsection)
            )
            rows = result.all()

            if not rows:
                return None

            # First row contains stats
            stat_model = rows[0][0]
            stats = self._model_to_subsection_stats(stat_model)

            # Collect tickets from all rows
            tickets = [
                self._model_to_ticket(ticket_model)
                for _, ticket_model in rows
                if ticket_model is not None
            ]

            return SubsectionTicketsAggregate(stats=stats, tickets=tickets)
