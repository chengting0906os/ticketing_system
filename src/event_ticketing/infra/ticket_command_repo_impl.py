import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.event_ticketing.domain.ticket_command_repo import TicketCommandRepo
from src.event_ticketing.domain.ticket_entity import Ticket, TicketStatus
from src.event_ticketing.infra.ticket_model import TicketModel
from src.shared.config.db_setting import get_asyncpg_pool
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
    async def create_batch(self, *, tickets: list[Ticket]) -> list[Ticket]:
        """Create tickets using Ticket objects (original interface)"""
        # Convert Ticket objects to tuples and delegate to tuple version
        ticket_tuples = [
            (
                ticket.event_id,
                ticket.section,
                ticket.subsection,
                ticket.row,
                ticket.seat,
                ticket.price,
                ticket.status.value,
            )
            for ticket in tickets
        ]

        return await self._create_batch_by_tuple(tickets=ticket_tuples)

    @Logger.io
    async def _create_batch_by_tuple(self, *, tickets: list[tuple]) -> list[Ticket]:
        """Create tickets using tuples for maximum performance

        Args:
            tickets: List of tuples (event_id, section, subsection, row, seat, price, status)
        """
        start_time = time.time()
        Logger.base.info(f'🚀 開始批量建立 {len(tickets):,} 張票 (COPY BINARY with Pool)...')

        if not tickets:
            return []

        # Use asyncpg connection pool for both COPY and FETCH operations
        async with (await get_asyncpg_pool()).acquire() as conn:
            # COPY operation
            copy_start = time.time()
            await conn.copy_records_to_table(
                'ticket',
                records=tickets,
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
            Logger.base.info(f'  📦 COPY 完成 ({copy_time:.3f}s)')

            # Fetch inserted tickets using the same connection
            fetch_start = time.time()
            rows = await conn.fetch(
                """
                SELECT id, event_id, section, subsection, row_number, seat_number, price, status,
                       buyer_id, reserved_at, created_at, updated_at
                FROM ticket
                WHERE id > (
                    SELECT COALESCE(MAX(id), 0) - $1 FROM ticket
                )
                ORDER BY id
            """,
                len(tickets),
            )

            fetch_time = time.time() - fetch_start
            Logger.base.info(f'  🔍 Fetch 完成 ({fetch_time:.3f}s)')

        # Convert to entities
        convert_start = time.time()
        all_created_tickets = []
        for row in rows:
            db_ticket = TicketModel(
                id=row['id'],
                event_id=row['event_id'],
                section=row['section'],
                subsection=row['subsection'],
                row_number=row['row_number'],
                seat_number=row['seat_number'],
                price=row['price'],
                status=row['status'],
                buyer_id=row['buyer_id'],
                reserved_at=row['reserved_at'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
            )
            all_created_tickets.append(self._to_entity(db_ticket))

        convert_time = time.time() - convert_start
        Logger.base.info(f'  🔄 Convert 完成 ({convert_time:.3f}s)')

        total_time = time.time() - start_time
        Logger.base.info(
            f'🎯 批量建立完成！總共 {len(all_created_tickets):,} 張票，耗時 {total_time:.3f}s'
        )
        Logger.base.info(f'📊 效能：{len(all_created_tickets) / total_time:.0f} 張票/秒')
        Logger.base.info(
            f'⚡ 分解時間：COPY={copy_time:.3f}s, Fetch={fetch_time:.3f}s, Convert={convert_time:.3f}s'
        )

        return all_created_tickets

    @Logger.io
    async def update_batch(self, *, tickets: list[Ticket]) -> list[Ticket]:
        if not tickets:
            return []

        # 收集所有要更新的 ticket IDs
        ticket_ids = [ticket.id for ticket in tickets if ticket.id is not None]
        if not ticket_ids:
            return []

        # 批量查詢現有的 tickets
        result = await self.session.execute(
            select(TicketModel).where(TicketModel.id.in_(ticket_ids))
        )
        existing_tickets = {db_ticket.id: db_ticket for db_ticket in result.scalars().all()}

        updated_tickets = []

        # 批量更新
        for ticket in tickets:
            if ticket.id and ticket.id in existing_tickets:
                db_ticket = existing_tickets[ticket.id]

                # 更新字段
                db_ticket.status = ticket.status.value
                db_ticket.buyer_id = ticket.buyer_id
                db_ticket.reserved_at = ticket.reserved_at
                if ticket.updated_at is not None:
                    db_ticket.updated_at = ticket.updated_at

                updated_tickets.append(self._to_entity(db_ticket))

        # 一次性 flush 所有更新
        if updated_tickets:
            await self.session.flush()

        return updated_tickets
