"""
Seat Initializing Command Repository Interface

座位初始化命令倉儲接口 - 負責座位初始化操作（測試用）
"""

from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID


class ISeatInitializingCommandRepo(ABC):
    """
    座位初始化命令倉儲接口

    職責：初始化座位狀態（主要用於測試）
    """

    @abstractmethod
    async def initialize_seat(
        self, *, seat_id: str, event_id: UUID, price: int, timestamp: Optional[str] = None
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
