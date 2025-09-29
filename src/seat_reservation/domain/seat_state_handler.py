"""
Seat State Handler Port
座位狀態處理器接口 - 抽象層定義
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class SeatStateHandler(ABC):
    """
    座位狀態處理器接口

    定義座位狀態管理的核心操作
    """

    @abstractmethod
    def get_seat_states(self, seat_ids: List[str], event_id: int) -> Dict[str, Dict]:
        pass

    @abstractmethod
    def get_available_seats_by_section(
        self, event_id: int, section: str, subsection: int, limit: Optional[int] = None
    ) -> List[Dict]:
        pass

    @abstractmethod
    def reserve_seats(
        self, seat_ids: List[str], booking_id: int, buyer_id: int, event_id: int
    ) -> Dict[str, bool]:
        pass

    @abstractmethod
    def release_seats(self, seat_ids: List[str], event_id: int) -> Dict[str, bool]:
        pass

    @abstractmethod
    def get_seat_price(self, seat_id: str, event_id: int) -> Optional[int]:
        pass
