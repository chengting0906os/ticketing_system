"""
Payment Finalizing Command Repository Interface

付款完成命令倉儲接口 - 負責完成付款操作
"""

from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID


class IPaymentFinalizingCommandRepo(ABC):
    """
    付款完成命令倉儲接口

    職責：將座位狀態從 RESERVED 轉為 SOLD
    """

    @abstractmethod
    async def finalize_payment(
        self, *, seat_id: str, event_id: UUID, timestamp: Optional[str] = None
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
