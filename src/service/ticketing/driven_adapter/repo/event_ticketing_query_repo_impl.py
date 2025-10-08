"""
Event Ticketing Query Repository Implementation - CQRS Read Side

統一的活動票務查詢倉儲實現
提供豐富的查詢接口，支持多種查詢視角和性能優化
"""

from contextlib import asynccontextmanager
from typing import AsyncContextManager, AsyncIterator, Callable, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import (
    Event,
    EventTicketingAggregate,
    Ticket,
    TicketStatus,
)
from src.service.ticketing.app.interface.i_event_ticketing_query_repo import (
    IEventTicketingQueryRepo,
)
from src.service.ticketing.driven_adapter.model.event_model import EventModel
from src.service.ticketing.driven_adapter.model.ticket_model import TicketModel
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.shared_kernel.domain.enum.event_status import EventStatus


class EventTicketingQueryRepoImpl(IEventTicketingQueryRepo):
    """Event Ticketing Query Repository Implementation - CQRS Read Side"""

    def __init__(
        self, session_factory: Callable[..., AsyncContextManager[AsyncSession]] | None = None
    ):
        self.session_factory = session_factory
        self.session: AsyncSession | None = None

    @asynccontextmanager
    async def _get_session(self) -> AsyncIterator[AsyncSession]:
        """
        Get session for query execution.

        If session is injected (from UoW), yield it directly without context management.
        Otherwise, use session_factory context manager.
        """
        if self.session is not None:
            # Session injected by UoW - use directly (no context manager needed)
            yield self.session
        elif self.session_factory is not None:
            # Use session_factory context manager
            async with self.session_factory() as session:
                yield session
        else:
            raise RuntimeError('No session or session_factory available')

    def _model_to_event(self, event_model: EventModel) -> Event:
        """將 EventModel 轉換為 Event 實體"""
        return Event(
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
        )

    def _model_to_ticket(self, ticket_model: TicketModel) -> Ticket:
        """將 TicketModel 轉換為 Ticket 實體"""
        return Ticket(
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

    @Logger.io
    async def get_event_aggregate_by_id(
        self, *, event_id: int
    ) -> Optional[EventTicketingAggregate]:
        """根據 ID 獲取完整的 Event Aggregate"""
        async with self._get_session() as session:
            # 查詢活動
            event_result = await session.execute(
                select(EventModel).where(EventModel.id == event_id)
            )
            event_model = event_result.scalar_one_or_none()

            if not event_model:
                return None

            # 查詢所有票務
            tickets_result = await session.execute(
                select(TicketModel).where(TicketModel.event_id == event_id)
            )
            ticket_models = tickets_result.scalars().all()

            # 轉換為領域實體
            event = self._model_to_event(event_model)
            tickets = [self._model_to_ticket(ticket_model) for ticket_model in ticket_models]

            aggregate = EventTicketingAggregate(event=event, tickets=tickets)

            Logger.base.info(
                f'🔍 [GET_AGGREGATE] Loaded event {event_id} with {len(tickets)} tickets'
            )
            return aggregate

    @Logger.io
    async def get_event_aggregate_by_id_with_available_tickets_only(
        self, *, event_id: int
    ) -> Optional[EventTicketingAggregate]:
        """根據 ID 獲取 Event Aggregate (只包含可用票務)"""
        async with self._get_session() as session:
            # 查詢活動
            event_result = await session.execute(
                select(EventModel).where(EventModel.id == event_id)
            )
            event_model = event_result.scalar_one_or_none()

            if not event_model:
                return None

            # 只查詢可用票務
            tickets_result = await session.execute(
                select(TicketModel)
                .where(TicketModel.event_id == event_id)
                .where(TicketModel.status == TicketStatus.AVAILABLE.value)
            )
            ticket_models = tickets_result.scalars().all()

            # 轉換為領域實體
            event = self._model_to_event(event_model)
            tickets = [self._model_to_ticket(ticket_model) for ticket_model in ticket_models]

            aggregate = EventTicketingAggregate(event=event, tickets=tickets)

            Logger.base.info(
                f'🎯 [GET_AVAILABLE] Loaded event {event_id} with {len(tickets)} available tickets'
            )
            return aggregate

    @Logger.io
    async def list_events_by_seller(self, *, seller_id: int) -> List[EventTicketingAggregate]:
        """獲取賣家的所有活動 (不包含 tickets，性能優化)"""
        async with self._get_session() as session:
            result = await session.execute(
                select(EventModel).where(EventModel.seller_id == seller_id)
            )
            event_models = result.scalars().all()

            aggregates = []
            for event_model in event_models:
                event = self._model_to_event(event_model)
                aggregate = EventTicketingAggregate(event=event, tickets=[])
                aggregates.append(aggregate)

            Logger.base.info(
                f'📋 [LIST_BY_SELLER] Found {len(aggregates)} events for seller {seller_id}'
            )
            return aggregates

    @Logger.io
    async def list_available_events(self) -> List[EventTicketingAggregate]:
        """獲取所有可用活動 (不包含 tickets，性能優化)"""
        async with self._get_session() as session:
            result = await session.execute(
                select(EventModel)
                .where(EventModel.is_active)
                .where(EventModel.status == EventStatus.AVAILABLE.value)
            )
            event_models = result.scalars().all()

            aggregates = []
            for event_model in event_models:
                event = self._model_to_event(event_model)
                aggregate = EventTicketingAggregate(event=event, tickets=[])
                aggregates.append(aggregate)

            Logger.base.info(f'🌟 [LIST_AVAILABLE] Found {len(aggregates)} available events')
            return aggregates

    @Logger.io
    async def get_tickets_by_event_and_section(
        self, *, event_id: int, section: str, subsection: int
    ) -> List[Ticket]:
        """獲取特定區域的票務"""
        async with self._get_session() as session:
            result = await session.execute(
                select(TicketModel)
                .where(TicketModel.event_id == event_id)
                .where(TicketModel.section == section)
                .where(TicketModel.subsection == subsection)
            )
            ticket_models = result.scalars().all()

            tickets = [self._model_to_ticket(ticket_model) for ticket_model in ticket_models]

            Logger.base.info(
                f'🎫 [GET_SECTION] Found {len(tickets)} tickets in section {section}-{subsection}'
            )
            return tickets

    @Logger.io
    async def get_available_tickets_by_event(self, *, event_id: int) -> List[Ticket]:
        """獲取活動的所有可用票務"""
        async with self._get_session() as session:
            result = await session.execute(
                select(TicketModel)
                .where(TicketModel.event_id == event_id)
                .where(TicketModel.status == TicketStatus.AVAILABLE.value)
            )
            ticket_models = result.scalars().all()

            tickets = [self._model_to_ticket(ticket_model) for ticket_model in ticket_models]

            Logger.base.info(f'✅ [GET_AVAILABLE_TICKETS] Found {len(tickets)} available tickets')
            return tickets

    @Logger.io
    async def get_reserved_tickets_by_event(self, *, event_id: int) -> List[Ticket]:
        """獲取活動的所有已預訂票務"""
        async with self._get_session() as session:
            result = await session.execute(
                select(TicketModel)
                .where(TicketModel.event_id == event_id)
                .where(TicketModel.status == TicketStatus.RESERVED.value)
            )
            ticket_models = result.scalars().all()

            tickets = [self._model_to_ticket(ticket_model) for ticket_model in ticket_models]

            Logger.base.info(f'📝 [GET_RESERVED_TICKETS] Found {len(tickets)} reserved tickets')
            return tickets

    @Logger.io
    async def get_tickets_by_buyer(self, *, buyer_id: int) -> List[Ticket]:
        """獲取購買者的所有票務"""
        async with self._get_session() as session:
            result = await session.execute(
                select(TicketModel).where(TicketModel.buyer_id == buyer_id)
            )
            ticket_models = result.scalars().all()

            tickets = [self._model_to_ticket(ticket_model) for ticket_model in ticket_models]

            Logger.base.info(
                f'👤 [GET_BUYER_TICKETS] Found {len(tickets)} tickets for buyer {buyer_id}'
            )
            return tickets

    @Logger.io
    async def get_tickets_by_ids(self, *, ticket_ids: List[int]) -> List[Ticket]:
        """根據 ID 列表獲取票務"""
        async with self._get_session() as session:
            result = await session.execute(
                select(TicketModel).where(TicketModel.id.in_(ticket_ids))
            )
            ticket_models = result.scalars().all()

            tickets = [self._model_to_ticket(ticket_model) for ticket_model in ticket_models]

            Logger.base.info(f'🎯 [GET_BY_IDS] Found {len(tickets)} tickets by IDs')
            return tickets

    @Logger.io
    async def check_tickets_exist_for_event(self, *, event_id: int) -> bool:
        """檢查活動是否已有票務"""
        async with self._get_session() as session:
            result = await session.execute(
                select(func.count(TicketModel.id)).where(TicketModel.event_id == event_id)
            )
            count = result.scalar()

            exists = (count or 0) > 0
            Logger.base.info(f'❓ [CHECK_TICKETS_EXIST] Event {event_id} has tickets: {exists}')
            return exists
