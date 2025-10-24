"""
Seat Reservation Event Publisher Interface
座位預訂事件發布器介面 - 定義事件發布的抽象
"""

from abc import ABC, abstractmethod
from typing import List


class ISeatReservationEventPublisher(ABC):
    """座位預訂事件發布器介面"""

    @abstractmethod
    async def publish_seats_reserved(
        self,
        *,
        booking_id: int,
        buyer_id: int,
        reserved_seats: List[str],
        total_price: int,
        event_id: int,
        ticket_details: List[dict],
    ) -> None:
        """
        發送座位預訂成功事件

        Args:
            ticket_details: Required list of dicts with seat_id and price
                           e.g., [{'seat_id': 'A-1-1-1', 'price': 1000}, ...]
        """
        pass

    @abstractmethod
    async def publish_reservation_failed(
        self,
        *,
        booking_id: int,
        buyer_id: int,
        error_message: str,
        event_id: int,
    ) -> None:
        """發送座位預訂失敗事件"""
        pass
