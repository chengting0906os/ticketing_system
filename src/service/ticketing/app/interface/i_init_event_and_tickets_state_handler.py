"""
Init Event And Tickets State Handler Interface

座位初始化狀態處理器接口 - Ticketing Service 的職責
"""

from abc import ABC, abstractmethod
from typing import Dict
from uuid import UUID


class IInitEventAndTicketsStateHandler(ABC):
    """
    座位初始化狀態處理器接口

    職責：
    - 從 seating_config 初始化所有座位到 Kvrocks
    - 建立 event_sections 索引
    - 建立 section_stats 統計
    """

    @abstractmethod
    async def initialize_seats_from_config(self, *, event_id: UUID, seating_config: Dict) -> Dict:
        """
        從 seating_config 初始化座位

        Args:
            event_id: 活動 ID
            seating_config: 座位配置

        Returns:
            {
                'success': True/False,
                'total_seats': 3000,
                'sections_count': 30,
                'error': None or error message
            }
        """
        pass
