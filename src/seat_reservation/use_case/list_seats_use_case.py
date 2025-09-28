"""
座位列表查詢用例
從 PostgreSQL 獲取座位基本信息，從 RocksDB 獲取實時狀態
"""

from typing import Dict, List

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.event_ticketing.domain.ticket_entity import Ticket, TicketStatus
from src.event_ticketing.infra.ticket_model import TicketModel
from src.seat_reservation.infra.rocksdb_monitor import RocksDBMonitor
from src.shared.config.db_setting import get_async_session
from src.shared.logging.loguru_io import Logger


class ListSeatsUseCase:
    """
    座位列表查詢用例

    結合 PostgreSQL 座位信息和 RocksDB 實時狀態
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.rocksdb_monitor = RocksDBMonitor()

    @classmethod
    def depends(cls, session: AsyncSession = Depends(get_async_session)):
        return cls(session=session)

    @Logger.io
    async def list_tickets_by_event_section_section(
        self, *, event_id: int, section: str, subsection: int
    ) -> List[Ticket]:
        """
        查詢指定活動、區域、子區域的所有座位
        優先使用 RocksDB 作為數據源
        """
        # 1. 檢查 RocksDB 是否可用
        if not self.rocksdb_monitor.is_available():
            Logger.base.warning('🔄 [SEAT_LIST] RocksDB not available, falling back to PostgreSQL')
            return await self._fallback_to_postgresql(event_id, section, subsection)

        try:
            # 2. 從 RocksDB 獲取所有座位狀態
            all_seats = self.rocksdb_monitor.get_all_seats(limit=5000)

            # 3. 過濾指定活動、區域、子區域的座位
            filtered_seats = []
            target_prefix = f'{section}-{subsection}-'

            for seat_state in all_seats:
                if seat_state.event_id == event_id and seat_state.seat_id.startswith(target_prefix):
                    filtered_seats.append(seat_state)

            # 4. 將 RocksDB SeatState 轉換為 Ticket 域實體
            tickets = []
            for seat_state in filtered_seats:
                try:
                    # 解析 seat_id 格式: "section-subsection-row-seat"
                    parts = seat_state.seat_id.split('-')
                    if len(parts) >= 4:
                        row = int(parts[2])
                        seat_num = int(parts[3])

                        # 狀態映射
                        status = TicketStatus.AVAILABLE
                        if seat_state.status == 'RESERVED':
                            status = TicketStatus.RESERVED
                        elif seat_state.status == 'SOLD':
                            status = TicketStatus.SOLD

                        ticket = Ticket(
                            event_id=event_id,
                            section=section,
                            subsection=subsection,
                            row=row,
                            seat=seat_num,
                            price=seat_state.price or 0,
                            status=status,
                            buyer_id=seat_state.buyer_id,
                            reserved_at=None,  # RocksDB 中的時間戳需要轉換
                        )
                        tickets.append(ticket)

                except (ValueError, IndexError) as e:
                    Logger.base.warning(
                        f'⚠️ [SEAT_LIST] Invalid seat_id format: {seat_state.seat_id}, error: {e}'
                    )
                    continue

            Logger.base.info(
                f'✅ [SEAT_LIST] Found {len(tickets)} seats from RocksDB for event={event_id}, section={section}, subsection={subsection}'
            )
            return tickets

        except Exception as e:
            Logger.base.error(f'❌ [SEAT_LIST] Error reading from RocksDB: {e}')
            return await self._fallback_to_postgresql(event_id, section, subsection)

    @Logger.io
    async def _fallback_to_postgresql(
        self, event_id: int, section: str, subsection: int
    ) -> List[Ticket]:
        """
        PostgreSQL 降級方案：從數據庫查詢並同步 RocksDB 狀態
        """
        # 從 PostgreSQL 查詢基本座位信息
        stmt = (
            select(TicketModel)
            .where(TicketModel.event_id == event_id)
            .where(TicketModel.section == section)
            .where(TicketModel.subsection == subsection)
        )
        result = await self.session.execute(stmt)
        db_tickets = result.scalars().all()

        # 轉換為域實體
        tickets = []
        for db_ticket in db_tickets:
            ticket = Ticket(
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
            tickets.append(ticket)

        # 嘗試同步 RocksDB 狀態（如果可用）
        tickets_with_rocksdb_status = await self.sync_ticket_status_with_rocksdb(tickets)
        return tickets_with_rocksdb_status

    @Logger.io
    async def sync_ticket_status_with_rocksdb(self, tickets: List[Ticket]) -> List[Ticket]:
        """
        同步票據狀態與 RocksDB

        Args:
            tickets: PostgreSQL 中的票據列表

        Returns:
            更新狀態後的票據列表
        """
        """
        實現與 RocksDB 的狀態同步
        """
        if not tickets:
            return tickets

        try:
            # 1. 檢查 RocksDB 是否可用
            if not self.rocksdb_monitor.is_available():
                Logger.base.warning('🔄 [SEAT_SYNC] RocksDB not available, using PostgreSQL status')
                return tickets

            # 2. 為每個票據生成 seat_id (format: "section-subsection-row-seat")
            ticket_seat_map: Dict[str, Ticket] = {}
            for ticket in tickets:
                seat_id = f'{ticket.section}-{ticket.subsection}-{ticket.row}-{ticket.seat}'
                ticket_seat_map[seat_id] = ticket

            # 3. 批量查詢 RocksDB 獲取實時狀態
            Logger.base.info(f'🔍 [SEAT_SYNC] Querying RocksDB for {len(ticket_seat_map)} seats')
            rocksdb_seats = self.rocksdb_monitor.get_all_seats(limit=5000)

            # 4. 創建 RocksDB 狀態映射
            rocksdb_status_map: Dict[str, str] = {}
            for seat_state in rocksdb_seats:
                rocksdb_status_map[seat_state.seat_id] = seat_state.status

            # 5. 更新票據狀態
            updated_count = 0
            for seat_id, ticket in ticket_seat_map.items():
                if seat_id in rocksdb_status_map:
                    rocksdb_status = rocksdb_status_map[seat_id]
                    # 狀態映射：RocksDB -> PostgreSQL
                    if rocksdb_status == 'AVAILABLE':
                        ticket.status = TicketStatus.AVAILABLE
                    elif rocksdb_status == 'RESERVED':
                        ticket.status = TicketStatus.RESERVED
                    elif rocksdb_status == 'SOLD':
                        ticket.status = TicketStatus.SOLD
                    else:
                        # 未知狀態，保持 PostgreSQL 原始狀態
                        Logger.base.warning(
                            f"⚠️ [SEAT_SYNC] Unknown RocksDB status '{rocksdb_status}' for seat {seat_id}"
                        )
                        continue
                    updated_count += 1
                else:
                    # RocksDB 中沒有記錄，可能尚未初始化，使用 PostgreSQL 狀態
                    Logger.base.debug(
                        f'🔍 [SEAT_SYNC] Seat {seat_id} not found in RocksDB, using PostgreSQL status'
                    )

            Logger.base.info(
                f'✅ [SEAT_SYNC] Updated {updated_count}/{len(tickets)} tickets with RocksDB status'
            )
            return tickets

        except Exception as e:
            Logger.base.error(f'❌ [SEAT_SYNC] Error syncing with RocksDB: {e}')
            # 發生錯誤時降級到 PostgreSQL 狀態
            Logger.base.warning(
                '🔄 [SEAT_SYNC] Falling back to PostgreSQL status due to RocksDB error'
            )
            return tickets
