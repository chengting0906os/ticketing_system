"""
座位可用性查詢用例
從 Kvrocks 獲取實時座位狀態，結合 PostgreSQL 獲取基本信息
"""

from dataclasses import dataclass
from typing import List

from src.platform.logging.loguru_io import Logger
from src.service.seat_reservation.app.interface.i_seat_state_query_handler import (
    ISeatStateQueryHandler,
)


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


class ListAllSubSectionStatusUseCase:
    """
    座位可用性查詢用例

    從 Kvrocks 獲取所有 section 的統計資訊
    """

    def __init__(self, seat_state_handler: ISeatStateQueryHandler):
        self.seat_state_handler = seat_state_handler

    @Logger.io
    async def execute(self, *, event_id: int) -> dict:
        """
        獲取活動所有 section 的統計資訊（從 Kvrocks 讀取）

        優化策略：
        1. 直接查詢 Kvrocks（獨立服務，可插隊查詢）
        2. 底層 Kvrocks 持久化（零數據丟失）
        3. 預期性能：~10-30ms（查詢 100 個 section，Pipeline 優化）
        4. 不受 Kafka backlog 影響

        Args:
            event_id: 活動 ID

        Returns:
            {
                "event_id": 1,
                "sections": {
                    "A-1": {"available": 100, "reserved": 20, "sold": 30, "total": 150},
                    ...
                },
                "total_sections": 100
            }
        """
        # 使用 SeatStateHandler 獲取統計資料
        all_sections = await self.seat_state_handler.list_all_subsection_status(event_id=event_id)

        Logger.base.info(
            f'📊 [USE-CASE] Retrieved {len(all_sections)} sections for event {event_id}'
        )

        return {'event_id': event_id, 'sections': all_sections, 'total_sections': len(all_sections)}
