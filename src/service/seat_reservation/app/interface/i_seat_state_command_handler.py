"""
Seat State Command Handler Interface

座位狀態命令處理器接口 - CQRS Command Side
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class ISeatStateCommandHandler(ABC):
    """
    座位狀態命令處理器接口 (CQRS Command)

    職責：只負責寫入操作，修改狀態
    """

    @abstractmethod
    async def reserve_seats(
        self, seat_ids: List[str], booking_id: int, buyer_id: int, event_id: int
    ) -> Dict[str, bool]:
        """
        預訂座位 (AVAILABLE -> RESERVED)

        Args:
            seat_ids: 座位 ID 列表
            booking_id: 訂單 ID
            buyer_id: 買家 ID
            event_id: 活動 ID

        Returns:
            Dict mapping seat_id to success status
        """
        pass

    @abstractmethod
    async def release_seats(self, seat_ids: List[str], event_id: int) -> Dict[str, bool]:
        """
        釋放座位 (RESERVED -> AVAILABLE)

        Args:
            seat_ids: 座位 ID 列表
            event_id: 活動 ID

        Returns:
            Dict mapping seat_id to success status
        """
        pass

    @abstractmethod
    async def finalize_payment(
        self, seat_id: str, event_id: int, timestamp: Optional[str] = None
    ) -> bool:
        """
        完成支付，將座位從 RESERVED 轉為 SOLD

        Args:
            seat_id: 座位 ID
            event_id: 活動 ID
            timestamp: 可選的時間戳

        Returns:
            是否成功
        """
        pass

    @abstractmethod
    async def initialize_seat(
        self, seat_id: str, event_id: int, price: int, timestamp: Optional[str] = None
    ) -> bool:
        """
        初始化座位狀態

        Args:
            seat_id: 座位 ID
            event_id: 活動 ID
            price: 座位價格
            timestamp: 可選的時間戳

        Returns:
            是否成功
        """
        pass
