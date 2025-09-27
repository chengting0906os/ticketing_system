"""
座位列表查詢用例
從 PostgreSQL 獲取座位基本信息，從 RocksDB 獲取實時狀態
"""

from typing import List
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.event_ticketing.domain.ticket_entity import Ticket
from src.shared.config.db_setting import get_async_session
from src.shared.logging.loguru_io import Logger


class ListSeatsUseCase:
    """
    座位列表查詢用例

    結合 PostgreSQL 座位信息和 RocksDB 實時狀態
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    @classmethod
    def depends(cls, session: AsyncSession = Depends(get_async_session)):
        return cls(session=session)

    @Logger.io
    async def list_tickets_by_event_section_section(
        self, *, event_id: int, section: str, subsection: int
    ) -> List[Ticket]:
        """
        查詢指定活動、區域、子區域的所有座位

        TODO(human): 實現 RocksDB 狀態同步邏輯
        """
        # 1. 從 PostgreSQL 查詢基本座位信息
        stmt = select(Ticket).filter(
            Ticket.event_id == event_id, Ticket.section == section, Ticket.subsection == subsection
        )
        result = await self.session.execute(stmt)
        tickets = result.scalars().all()

        # TODO(human) - 在這裡實現從 RocksDB 同步座位狀態的邏輯
        # 1. 為每個票據生成 seat_id (format: "section-subsection-row-seat")
        # 2. 批量查詢 RocksDB 獲取實時狀態
        # 3. 更新 tickets 的狀態字段
        # 4. 返回包含實時狀態的票據列表

        # 暫時直接返回 PostgreSQL 數據，等待人工實現 RocksDB 同步
        return list(tickets)

    @Logger.io
    async def sync_ticket_status_with_rocksdb(self, tickets: List[Ticket]) -> List[Ticket]:
        """
        同步票據狀態與 RocksDB

        Args:
            tickets: PostgreSQL 中的票據列表

        Returns:
            更新狀態後的票據列表
        """
        # TODO(human) - 實現與 RocksDB 的狀態同步
        # 1. 生成所有座位的 seat_id
        # 2. 調用 RocksDB 查詢接口
        # 3. 更新每個 ticket 的狀態

        # 暫時直接返回原始數據
        return tickets
