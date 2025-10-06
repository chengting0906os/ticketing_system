"""
Seat State Handler Port
座位狀態處理器接口 - 抽象層定義
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class ISeatStateHandler(ABC):
    """
    座位狀態處理器接口

    定義座位狀態管理的核心操作
    注意：所有方法都是異步的，因為底層需要訪問 Redis/數據庫
    """

    @abstractmethod
    async def get_seat_states(self, seat_ids: List[str], event_id: int) -> Dict[str, Dict]:
        pass

    @abstractmethod
    async def get_available_seats_by_section(
        self, event_id: int, section: str, subsection: int, limit: Optional[int] = None
    ) -> List[Dict]:
        pass

    @abstractmethod
    async def reserve_seats(
        self, seat_ids: List[str], booking_id: int, buyer_id: int, event_id: int
    ) -> Dict[str, bool]:
        pass

    @abstractmethod
    async def release_seats(self, seat_ids: List[str], event_id: int) -> Dict[str, bool]:
        pass

    @abstractmethod
    async def get_seat_price(self, seat_id: str, event_id: int) -> Optional[int]:
        pass

    @abstractmethod
    async def initialize_seat(
        self, seat_id: str, event_id: int, price: int, timestamp: Optional[str] = None
    ) -> bool:
        """初始化座位狀態"""
        pass

    @abstractmethod
    async def finalize_payment(
        self, seat_id: str, event_id: int, timestamp: Optional[str] = None
    ) -> bool:
        """完成支付，將座位從 RESERVED 轉為 SOLD"""
        pass

    @abstractmethod
    async def list_all_subsection_status(self, event_id: int) -> Dict[str, Dict]:
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
    async def initialize_seats_from_config(self, *, event_id: int, seating_config: dict) -> dict:
        """
        從 seating_config 直接初始化所有座位（單一 Lua 腳本）

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
