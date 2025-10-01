"""
座位可用性查詢用例
從 Kvrocks 獲取實時座位狀態，結合 PostgreSQL 獲取基本信息
"""

from dataclasses import dataclass
from typing import Dict, List

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.platform.config.db_setting import get_async_session
from src.platform.logging.loguru_io import Logger


@dataclass
class SubsectionAvailability:
    """子區域可用性信息"""

    subsection: int
    total_seats: int
    available_seats: int
    status: str


@dataclass
class PriceGroupAvailability:
    """價格組可用性信息"""

    price: int
    subsections: List[SubsectionAvailability]


@dataclass
class EventAvailabilityStatus:
    """活動整體可用性狀態"""

    event_id: int
    price_groups: List[PriceGroupAvailability]


class GetSeatAvailabilityUseCase:
    """
    座位可用性查詢用例

    結合 Kvrocks 實時狀態和 PostgreSQL 基本信息
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    @classmethod
    def depends(cls, session: AsyncSession = Depends(get_async_session)):
        return cls(session=session)

    @Logger.io
    async def get_event_status_with_all_subsections_tickets_count(
        self, *, event_id: int
    ) -> EventAvailabilityStatus:
        """
        獲取活動所有子區域的座位狀態

        TODO(human): 實現 Kvrocks 狀態聚合邏輯
        """
        # TODO(human) - 在這裡實現從 Kvrocks 獲取實時座位狀態的邏輯
        # 1. 從 PostgreSQL 獲取活動的座位配置信息
        # 2. 查詢 Kvrocks 獲取每個座位的實時狀態 (AVAILABLE/RESERVED/SOLD)
        # 3. 按價格和子區域聚合可用座位數量
        # 4. 返回 EventAvailabilityStatus 對象

        # 暫時返回模擬數據，等待人工實現
        mock_subsection = SubsectionAvailability(
            subsection=1, total_seats=6, available_seats=4, status='available'
        )

        mock_price_group = PriceGroupAvailability(price=1000, subsections=[mock_subsection])

        return EventAvailabilityStatus(event_id=event_id, price_groups=[mock_price_group])

    @Logger.io
    async def get_seat_status_from_kvrocks(self, *, seat_ids: List[str]) -> Dict[str, str]:
        """
        從 Kvrocks 批量獲取座位狀態

        Args:
            seat_ids: 座位ID列表 (格式: "section-subsection-row-seat")

        Returns:
            Dict[seat_id, status] - 座位狀態映射
        """
        # TODO(human) - 實現從 Kvrocks 批量查詢座位狀態
        # 需要與 Quix Streams 應用集成，或者直接訪問 Kvrocks 存儲

        # 暫時返回模擬數據
        return {seat_id: 'AVAILABLE' for seat_id in seat_ids}
