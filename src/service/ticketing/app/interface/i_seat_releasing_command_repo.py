"""
Seat Releasing Command Repository Interface

座位釋放命令倉儲接口 - 負責座位釋放操作
"""

from abc import ABC, abstractmethod
from typing import Dict, List
from uuid import UUID


class ISeatReleasingCommandRepo(ABC):
    """
    座位釋放命令倉儲接口

    職責：釋放已預訂的座位（補償操作）
    """

    @abstractmethod
    async def release_seats(self, *, seat_ids: List[str], event_id: UUID) -> Dict[str, bool]:
        """
        釋放座位 (RESERVED -> AVAILABLE)

        Args:
            seat_ids: 座位 ID 列表
            event_id: 活動 ID

        Returns:
            Dict mapping seat_id to success status
        """
        pass
