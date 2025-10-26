"""
Booking and Reserving Command Repository Interface

座位預訂命令倉儲接口 - 負責座位預訂操作
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from uuid import UUID


class IBookingAndReservingCommandRepo(ABC):
    """
    座位預訂命令倉儲接口

    職責：負責座位預訂的寫入操作
    - Manual mode: 用戶手動選擇座位
    - Best available mode: 系統自動分配最佳座位
    """

    @abstractmethod
    async def reserve_seats_atomic(
        self,
        *,
        event_id: UUID,
        booking_id: UUID,
        buyer_id: UUID,
        mode: str,  # 'manual' or 'best_available'
        seat_ids: Optional[List[str]] = None,  # for manual mode
        section: Optional[str] = None,  # for best_available mode
        subsection: Optional[int] = None,  # for best_available mode
        quantity: Optional[int] = None,  # for best_available mode
    ) -> Dict:
        """
        原子性預訂座位

        Args:
            event_id: 活動 ID
            booking_id: 訂單 ID
            buyer_id: 買家 ID
            mode: 預訂模式 ('manual' 或 'best_available')
            seat_ids: 手動模式的座位 ID 列表
            section: 自動模式的區域 (e.g., 'A')
            subsection: 自動模式的子區域編號 (e.g., 1)
            quantity: 自動模式需要的連續座位數量

        Returns:
            Dict with keys:
                - success: bool
                - reserved_seats: List[str] (座位 ID 列表)
                - ticket_price: int (票價)
                - error_message: Optional[str]
        """
        pass
