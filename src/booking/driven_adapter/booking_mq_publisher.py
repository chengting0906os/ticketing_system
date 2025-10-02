"""
Booking Event Publisher Port
遵循 Clean Architecture - Use Case 層不應直接依賴 Infrastructure
"""

from abc import ABC, abstractmethod
from typing import Any


class BookingMqPublisher(ABC):
    """
    訂單消息隊列發布接口

    這是一個 Port (在 Hexagonal Architecture 中)
    Use Case 層依賴這個接口，而不是具體實現
    """

    @abstractmethod
    async def publish_ticket_reserved_request(self, booking_event: Any, partition_key: str) -> None:
        """發布票據預訂請求事件，觸發 seat_reservation 服務處理"""
        pass

    @abstractmethod
    async def publish_ticket_cancelled(self, booking_event: Any, partition_key: str) -> None:
        """發布票據取消事件，通知 seat_reservation 服務釋放座位"""
        pass
