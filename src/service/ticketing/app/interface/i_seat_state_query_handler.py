"""
Seat State Query Handler Interface - Shared Kernel

座位狀態查詢處理器接口 - CQRS Query Side
供 Ticketing 和 Seat Reservation 兩個 bounded context 使用
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from uuid import UUID


class ISeatStateQueryHandler(ABC):
    """
    座位狀態查詢處理器接口 (CQRS Query)

    職責：只負責讀取操作，不修改狀態
    """

    @abstractmethod
    async def get_seat_states(self, seat_ids: List[str], event_id: UUID) -> Dict[str, Dict]:
        """
        獲取指定座位的狀態

        Args:
            seat_ids: 座位 ID 列表
            event_id: 活動 ID

        Returns:
            Dict mapping seat_id to seat state
        """
        pass

    @abstractmethod
    async def get_seat_price(self, seat_id: str, event_id: UUID) -> Optional[int]:
        """
        獲取座位價格

        Args:
            seat_id: 座位 ID
            event_id: 活動 ID

        Returns:
            座位價格，None 表示座位不存在
        """
        pass

    @abstractmethod
    async def list_all_subsection_status(self, event_id: UUID) -> Dict[str, Dict]:
        """
        獲取活動所有 subsection 的統計資訊

        Args:
            event_id: 活動 ID

        Returns:
            Dict mapping section_id to stats:
            {
                "A-1": {"available": 100, "reserved": 20, "sold": 30, "total": 150},
                ...
            }
        """
        pass

    @abstractmethod
    async def list_all_subsection_seats(
        self, event_id: UUID, section: str, subsection: int
    ) -> List[Dict]:
        """
        獲取指定 subsection 的所有座位（包括 available, reserved, sold）

        Args:
            event_id: 活動 ID
            section: 區域代碼
            subsection: 子區域編號

        Returns:
            座位列表，每個座位包含 section, subsection, row, seat_num, price, status, seat_identifier
        """
        pass
