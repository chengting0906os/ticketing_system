"""
Event Ticketing Command Repository Implementation - CQRS Write Side

統一的活動票務命令倉儲實現
使用 EventTicketingAggregate 作為操作單位，保證聚合一致性
"""

from datetime import datetime, timezone
import time
from typing import Any, AsyncContextManager, Callable, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import (
    EventTicketingAggregate,
    Ticket,
    TicketStatus,
)
from src.service.ticketing.app.interface.i_event_ticketing_command_repo import (
    EventTicketingCommandRepo,
)
from src.service.ticketing.driven_adapter.model.event_model import EventModel
from src.service.ticketing.driven_adapter.model.ticket_model import TicketModel
from src.platform.config.db_setting import get_asyncpg_pool
from src.platform.logging.loguru_io import Logger


class EventTicketingCommandRepoImpl(EventTicketingCommandRepo):
    """Event Ticketing Command Repository Implementation"""

    def __init__(self, session_factory: Callable[..., AsyncContextManager[AsyncSession]]):
        self.session_factory = session_factory

    @Logger.io
    async def create_event_aggregate(
        self, *, event_aggregate: EventTicketingAggregate
    ) -> EventTicketingAggregate:
        """創建 Event Aggregate (包含 Event 和 Tickets)"""
        async with self.session_factory() as session:
            # 1. 保存 Event
            event_model = EventModel(
                name=event_aggregate.event.name,
                description=event_aggregate.event.description,
                seller_id=event_aggregate.event.seller_id,
                venue_name=event_aggregate.event.venue_name,
                seating_config=event_aggregate.event.seating_config,
                is_active=event_aggregate.event.is_active,
                status=event_aggregate.event.status.value,
            )

            session.add(event_model)
            await session.flush()  # 獲取 ID

            # 2. 更新 Event 實體的 ID
            event_aggregate.event.id = event_model.id

            # 3. 保存 Tickets (如果有的話)
            if event_aggregate.tickets:
                ticket_models = []
                for ticket in event_aggregate.tickets:
                    ticket_model = TicketModel(
                        event_id=event_model.id,
                        section=ticket.section,
                        subsection=ticket.subsection,
                        row_number=ticket.row,
                        seat_number=ticket.seat,
                        price=ticket.price,
                        status=ticket.status.value,
                        buyer_id=ticket.buyer_id,
                        reserved_at=ticket.reserved_at,
                    )
                    ticket_models.append(ticket_model)
                    session.add(ticket_model)

                await session.flush()

                # 更新 Ticket 實體的 ID
                for i, ticket_model in enumerate(ticket_models):
                    event_aggregate.tickets[i].id = ticket_model.id

            # 提交變更確保 asyncpg 能看到
            await session.commit()

            Logger.base.info(
                f'🗾 [CREATE_AGGREGATE] Created event {event_model.id} with {len(event_aggregate.tickets)} tickets'
            )

            return event_aggregate

    @Logger.io
    async def create_event_aggregate_with_batch_tickets(
        self,
        *,
        event_aggregate: EventTicketingAggregate,
        ticket_tuples: Optional[List[tuple]] = None,
    ) -> EventTicketingAggregate:
        """創建 Event Aggregate 使用高效能批量票務創建

        注意：這個方法假設 Event 已經存在並且有 ID
        只會批量創建 tickets，不會重新創建 event
        """
        # 檢查 Event 是否已經有 ID（已經持久化）
        if not event_aggregate.event.id:
            raise ValueError('Event must be persisted before using batch ticket creation')

        # 高效能批量創建票務
        if event_aggregate.tickets:
            Logger.base.info(
                f'🚀 [BATCH_CREATE] Using high-performance batch creation for {len(event_aggregate.tickets)} tickets'
            )

            start_time = time.time()

            # 使用傳入的批量數據，如果沒有則從 tickets 生成
            if ticket_tuples is None:
                ticket_tuples = [
                    (
                        event_aggregate.event.id,  # 使用已存在的 event_id
                        ticket.section,
                        ticket.subsection,
                        ticket.row,
                        ticket.seat,
                        ticket.price,
                        ticket.status.value,
                    )
                    for ticket in event_aggregate.tickets
                ]
            else:
                Logger.base.info('📦 [BATCH_CREATE] Using pre-generated ticket tuples')

            actual_tuples = ticket_tuples

            # 使用 asyncpg connection pool 進行 COPY 操作
            async with (await get_asyncpg_pool()).acquire() as conn:
                # COPY operation
                copy_start = time.time()
                await conn.copy_records_to_table(
                    'ticket',
                    records=actual_tuples,
                    columns=[
                        'event_id',
                        'section',
                        'subsection',
                        'row_number',
                        'seat_number',
                        'price',
                        'status',
                    ],
                )
                copy_time = time.time() - copy_start
                Logger.base.info(f'  📦 [BATCH_CREATE] COPY completed ({copy_time:.3f}s)')

                # Fetch inserted tickets
                fetch_start = time.time()
                rows = await conn.fetch(
                    """
                    SELECT id, event_id, section, subsection, row_number, seat_number, price, status,
                           buyer_id, reserved_at, created_at, updated_at
                    FROM ticket
                    WHERE event_id = $1
                    ORDER BY id
                """,
                    event_aggregate.event.id,
                )
                fetch_time = time.time() - fetch_start
                Logger.base.info(f'  🔍 [BATCH_CREATE] Fetch completed ({fetch_time:.3f}s)')

            # 更新 Ticket 實體的 ID
            convert_start = time.time()
            for i, row in enumerate(rows):
                if i < len(event_aggregate.tickets):
                    event_aggregate.tickets[i].id = row['id']

            convert_time = time.time() - convert_start
            total_time = time.time() - start_time

            Logger.base.info(
                f'🎯 [BATCH_CREATE] Completed! {len(event_aggregate.tickets):,} tickets in {total_time:.3f}s'
            )
            Logger.base.info(
                f'📊 [BATCH_CREATE] Performance: {len(event_aggregate.tickets) / total_time:.0f} tickets/sec'
            )
            Logger.base.info(
                f'⚡ [BATCH_CREATE] Breakdown: COPY={copy_time:.3f}s, Fetch={fetch_time:.3f}s, Convert={convert_time:.3f}s'
            )

        return event_aggregate

    @Logger.io
    async def update_event_aggregate(
        self, *, event_aggregate: EventTicketingAggregate
    ) -> EventTicketingAggregate:
        """更新 Event Aggregate"""
        async with self.session_factory() as session:
            if not event_aggregate.event.id:
                raise ValueError('Event must have an ID to be updated')

            # 1. 更新 Event
            await session.execute(
                update(EventModel)
                .where(EventModel.id == event_aggregate.event.id)
                .values(
                    name=event_aggregate.event.name,
                    description=event_aggregate.event.description,
                    venue_name=event_aggregate.event.venue_name,
                    seating_config=event_aggregate.event.seating_config,
                    is_active=event_aggregate.event.is_active,
                    status=event_aggregate.event.status.value,
                )
            )

            # 2. 更新 Tickets
            for ticket in event_aggregate.tickets:
                if ticket.id:
                    # 更新現有票務
                    await session.execute(
                        update(TicketModel)
                        .where(TicketModel.id == ticket.id)
                        .values(
                            status=ticket.status.value,
                            buyer_id=ticket.buyer_id,
                            updated_at=datetime.now(timezone.utc),
                            reserved_at=ticket.reserved_at,
                        )
                    )
                else:
                    # 新增票務
                    ticket_model = TicketModel(
                        event_id=event_aggregate.event.id,
                        section=ticket.section,
                        subsection=ticket.subsection,
                        row_number=ticket.row,
                        seat_number=ticket.seat,
                        price=ticket.price,
                        status=ticket.status.value,
                        buyer_id=ticket.buyer_id,
                        reserved_at=ticket.reserved_at,
                    )
                    session.add(ticket_model)
                    await session.flush()
                    ticket.id = ticket_model.id

            Logger.base.info(
                f'🔄 [UPDATE_AGGREGATE] Updated event {event_aggregate.event.id} with {len(event_aggregate.tickets)} tickets'
            )

            return event_aggregate

    @Logger.io
    async def update_tickets_status(
        self,
        *,
        ticket_ids: List[int],
        status: TicketStatus,
        buyer_id: Optional[int] = None,
    ) -> List[Ticket]:
        """批量更新票務狀態"""
        async with self.session_factory() as session:
            # 更新票務狀態
            update_values: Dict[str, Any] = {
                'status': status.value,
            }

            if buyer_id is not None:
                update_values['buyer_id'] = buyer_id

            if status == TicketStatus.RESERVED:
                update_values['reserved_at'] = datetime.now(timezone.utc)
            elif status == TicketStatus.AVAILABLE:
                update_values['buyer_id'] = None
                update_values['reserved_at'] = None

            await session.execute(
                update(TicketModel).where(TicketModel.id.in_(ticket_ids)).values(**update_values)
            )

            # 查詢更新後的票務
            result = await session.execute(
                select(TicketModel).where(TicketModel.id.in_(ticket_ids))
            )
            ticket_models = result.scalars().all()

            tickets = []
            for model in ticket_models:
                ticket = Ticket(
                    event_id=model.event_id,
                    section=model.section,
                    subsection=model.subsection,
                    row=model.row_number,
                    seat=model.seat_number,
                    price=model.price,
                    status=TicketStatus(model.status),
                    buyer_id=model.buyer_id,
                    id=model.id,
                    created_at=model.created_at,
                    updated_at=model.updated_at,
                    reserved_at=model.reserved_at,
                )
                tickets.append(ticket)

            Logger.base.info(f'🎫 [UPDATE_STATUS] Updated {len(tickets)} tickets to {status.value}')
            return tickets

    @Logger.io
    async def delete_event_aggregate(self, *, event_id: int) -> bool:
        """刪除 Event Aggregate (cascade delete tickets)"""
        async with self.session_factory() as session:
            try:
                # 先刪除票務
                await session.execute(update(TicketModel).where(TicketModel.event_id == event_id))

                # 然後刪除活動
                result = await session.execute(update(EventModel).where(EventModel.id == event_id))

                success = result.rowcount > 0
                Logger.base.info(f'🗑️ [DELETE_AGGREGATE] Deleted event {event_id}: {success}')
                return success

            except Exception as e:
                Logger.base.error(f'❌ [DELETE_AGGREGATE] Failed to delete event {event_id}: {e}')
                return False

    @Logger.io
    async def release_tickets_from_booking(
        self, *, event_id: int, ticket_ids: List[int], booking_id: int
    ) -> List[Ticket]:
        """從訂單釋放票務"""
        return await self.update_tickets_status(
            ticket_ids=ticket_ids, status=TicketStatus.AVAILABLE
        )

    @Logger.io
    async def finalize_tickets_as_sold(
        self, *, event_id: int, ticket_ids: List[int], booking_id: int
    ) -> List[Ticket]:
        """將票務標記為已售出"""
        return await self.update_tickets_status(ticket_ids=ticket_ids, status=TicketStatus.SOLD)
