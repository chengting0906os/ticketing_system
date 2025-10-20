"""
Event Ticketing Command Repository Implementation - CQRS Write Side (Raw SQL with asyncpg)

統一的活動票務命令倉儲實現
使用 EventTicketingAggregate 作為操作單位，保證聚合一致性

Performance: Using raw SQL with asyncpg for maximum performance
"""

from datetime import datetime, timezone
import json
import time
from typing import List, Optional

from src.platform.database.db_setting import get_asyncpg_pool
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_event_ticketing_command_repo import (
    IEventTicketingCommandRepo,
)
from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import (
    EventTicketingAggregate,
    Ticket,
    TicketStatus,
)


class EventTicketingCommandRepoImpl(IEventTicketingCommandRepo):
    """Event Ticketing Command Repository Implementation (Raw SQL with asyncpg)"""

    def __init__(self):
        pass  # No session needed for raw SQL approach

    @Logger.io
    async def create_event_aggregate(
        self, *, event_aggregate: EventTicketingAggregate
    ) -> EventTicketingAggregate:
        """創建 Event Aggregate (包含 Event 和 Tickets)"""
        async with (await get_asyncpg_pool()).acquire() as conn:
            async with conn.transaction():
                # 1. 保存 Event
                event_row = await conn.fetchrow(
                    """
                    INSERT INTO event (
                        name, description, seller_id, venue_name,
                        seating_config, is_active, status
                    )
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
                    RETURNING id, name, description, seller_id, venue_name,
                              seating_config, is_active, status
                    """,
                    event_aggregate.event.name,
                    event_aggregate.event.description,
                    event_aggregate.event.seller_id,
                    event_aggregate.event.venue_name,
                    json.dumps(event_aggregate.event.seating_config),
                    event_aggregate.event.is_active,
                    event_aggregate.event.status.value,
                )

                # 2. 更新 Event 實體的 ID
                event_aggregate.event.id = event_row['id']

                # 3. 保存 Tickets (如果有的話)
                if event_aggregate.tickets:
                    ticket_records = [
                        (
                            event_row['id'],
                            ticket.section,
                            ticket.subsection,
                            ticket.row,
                            ticket.seat,
                            ticket.price,
                            ticket.status.value,
                            ticket.buyer_id,
                            ticket.reserved_at,
                        )
                        for ticket in event_aggregate.tickets
                    ]

                    await conn.executemany(
                        """
                        INSERT INTO ticket (
                            event_id, section, subsection, row_number, seat_number,
                            price, status, buyer_id, reserved_at
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        """,
                        ticket_records,
                    )

                    # 獲取插入的 ticket IDs
                    ticket_rows = await conn.fetch(
                        """
                        SELECT id, event_id, section, subsection, row_number, seat_number,
                               price, status, buyer_id, reserved_at, created_at, updated_at
                        FROM ticket
                        WHERE event_id = $1
                        ORDER BY id
                        """,
                        event_row['id'],
                    )

                    # 更新 Ticket 實體的 ID
                    for i, ticket_row in enumerate(ticket_rows):
                        if i < len(event_aggregate.tickets):
                            event_aggregate.tickets[i].id = ticket_row['id']

                Logger.base.info(
                    f'🗾 [CREATE_AGGREGATE] Created event {event_row["id"]} with {len(event_aggregate.tickets)} tickets'
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
        if not event_aggregate.event.id:
            raise ValueError('Event must have an ID to be updated')

        async with (await get_asyncpg_pool()).acquire() as conn:
            async with conn.transaction():
                # 1. 更新 Event
                await conn.execute(
                    """
                    UPDATE event
                    SET name = $1,
                        description = $2,
                        venue_name = $3,
                        seating_config = $4::jsonb,
                        is_active = $5,
                        status = $6
                    WHERE id = $7
                    """,
                    event_aggregate.event.name,
                    event_aggregate.event.description,
                    event_aggregate.event.venue_name,
                    json.dumps(event_aggregate.event.seating_config),
                    event_aggregate.event.is_active,
                    event_aggregate.event.status.value,
                    event_aggregate.event.id,
                )

                # 2. 更新 Tickets
                for ticket in event_aggregate.tickets:
                    if ticket.id:
                        # 更新現有票務
                        await conn.execute(
                            """
                            UPDATE ticket
                            SET status = $1,
                                buyer_id = $2,
                                reserved_at = $3,
                                updated_at = $4
                            WHERE id = $5
                            """,
                            ticket.status.value,
                            ticket.buyer_id,
                            ticket.reserved_at,
                            datetime.now(timezone.utc),
                            ticket.id,
                        )
                    else:
                        # 新增票務
                        ticket_row = await conn.fetchrow(
                            """
                            INSERT INTO ticket (
                                event_id, section, subsection, row_number, seat_number,
                                price, status, buyer_id, reserved_at
                            )
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                            RETURNING id
                            """,
                            event_aggregate.event.id,
                            ticket.section,
                            ticket.subsection,
                            ticket.row,
                            ticket.seat,
                            ticket.price,
                            ticket.status.value,
                            ticket.buyer_id,
                            ticket.reserved_at,
                        )
                        ticket.id = ticket_row['id']

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
        if not ticket_ids:
            return []

        async with (await get_asyncpg_pool()).acquire() as conn:
            now = datetime.now(timezone.utc)

            if status == TicketStatus.RESERVED:
                if buyer_id is None:
                    raise ValueError('buyer_id is required when updating to RESERVED')
                rows = await conn.fetch(
                    """
                    UPDATE ticket
                    SET status = 'reserved',
                        buyer_id = $1,
                        reserved_at = $2,
                        updated_at = $3
                    WHERE id = ANY($4::int[])
                    RETURNING id, event_id, section, subsection, row_number, seat_number,
                              price, status, buyer_id, reserved_at, created_at, updated_at
                    """,
                    buyer_id,
                    now,
                    now,
                    ticket_ids,
                )
                Logger.base.info(
                    f'🎫 [AVAILABLE→RESERVED] Updated {len(rows)} tickets for buyer {buyer_id}'
                )
            elif status == TicketStatus.AVAILABLE:
                rows = await conn.fetch(
                    """
                    UPDATE ticket
                    SET status = 'available',
                        buyer_id = NULL,
                        reserved_at = NULL,
                        updated_at = $1
                    WHERE id = ANY($2::int[])
                    RETURNING id, event_id, section, subsection, row_number, seat_number,
                              price, status, buyer_id, reserved_at, created_at, updated_at
                    """,
                    now,
                    ticket_ids,
                )
                Logger.base.info(f'🎫 [RESERVED→AVAILABLE] Released {len(rows)} tickets')
            elif status == TicketStatus.SOLD:
                rows = await conn.fetch(
                    """
                    UPDATE ticket
                    SET status = 'sold',
                        updated_at = $1
                    WHERE id = ANY($2::int[])
                    RETURNING id, event_id, section, subsection, row_number, seat_number,
                              price, status, buyer_id, reserved_at, created_at, updated_at
                    """,
                    now,
                    ticket_ids,
                )
                Logger.base.info(f'🎫 [RESERVED→SOLD] Finalized {len(rows)} tickets')
            else:
                raise ValueError(f'Unsupported status transition: {status}')

            return [
                Ticket(
                    event_id=row['event_id'],
                    section=row['section'],
                    subsection=row['subsection'],
                    row=row['row_number'],
                    seat=row['seat_number'],
                    price=row['price'],
                    status=TicketStatus(row['status']),
                    buyer_id=row['buyer_id'],
                    id=row['id'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    reserved_at=row['reserved_at'],
                )
                for row in rows
            ]

    @Logger.io
    async def delete_event_aggregate(self, *, event_id: int) -> bool:
        """
        刪除 Event Aggregate (cascade delete tickets)

        Used for compensating transactions when Kvrocks initialization fails.
        """
        async with (await get_asyncpg_pool()).acquire() as conn:
            try:
                async with conn.transaction():
                    # 先刪除票務
                    tickets_result = await conn.execute(
                        """
                        DELETE FROM ticket
                        WHERE event_id = $1
                        """,
                        event_id,
                    )

                    # 然後刪除活動
                    event_result = await conn.execute(
                        """
                        DELETE FROM event
                        WHERE id = $1
                        """,
                        event_id,
                    )

                    # 解析刪除的行數 (格式: "DELETE n")
                    tickets_count = int(tickets_result.split()[-1]) if tickets_result else 0
                    event_count = int(event_result.split()[-1]) if event_result else 0

                    success = event_count > 0
                    Logger.base.info(
                        f'🗑️ [DELETE_AGGREGATE] Deleted event {event_id}: '
                        f'{tickets_count} tickets, {event_count} event'
                    )
                    return success

            except Exception as e:
                Logger.base.error(f'❌ [DELETE_AGGREGATE] Failed to delete event {event_id}: {e}')
                return False
