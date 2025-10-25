"""
Seat Reservation Event Publisher Interface
座位預訂事件發布器介面 - 定義事件發布的抽象
"""

from abc import ABC, abstractmethod
from typing import List
from uuid import UUID


class ISeatReservationEventPublisher(ABC):
    """座位預訂事件發布器介面"""

    @abstractmethod
    async def publish_seats_reserved(
        self,
        *,
        booking_id: UUID,
        buyer_id: UUID,
        reserved_seats: List[str],
        total_price: int,
        event_id: UUID,
        ticket_details: List[dict],
        seat_selection_mode: str,
    ) -> None:
        """
        發送座位預訂成功事件

        Args:
            ticket_details: Required list of dicts with seat_id and price
                           e.g., [{'seat_id': 'A-1-1-1', 'price': 1000}, ...]
            seat_selection_mode: 'manual' or 'best_available'
        """
        pass

    @abstractmethod
    async def publish_reservation_failed(
        self,
        *,
        booking_id: UUID,
        buyer_id: UUID,
        error_message: str,
        event_id: UUID,
    ) -> None:
        """發送座位預訂失敗事件"""
        pass
