"""
Seat Availability Query Handler Interface

座位可用性查詢處理器接口 - Used by ticketing service to check seat availability
before creating bookings (Fail Fast principle)
"""

from abc import ABC, abstractmethod
from uuid import UUID


class ISeatAvailabilityQueryHandler(ABC):
    """
    座位可用性查詢處理器接口

    職責：讓 ticketing service 在建立 booking 前先檢查座位是否足夠
    這是跨服務的查詢接口，遵循 Fail Fast 原則
    """

    @abstractmethod
    async def check_subsection_availability(
        self, *, event_id: UUID, section: str, subsection: int, required_quantity: int
    ) -> bool:
        """
        檢查指定 subsection 是否有足夠的可用座位

        Args:
            event_id: 活動 ID
            section: 區域代碼 (e.g., 'A', 'B')
            subsection: 子區域編號 (e.g., 1, 2)
            required_quantity: 需要的座位數量

        Returns:
            True if enough seats available, False otherwise

        Note:
            This checks 'available' seats only, not 'reserved' or 'sold'
        """
        pass
