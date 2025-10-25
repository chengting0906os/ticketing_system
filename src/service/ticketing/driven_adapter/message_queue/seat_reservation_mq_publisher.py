"""
Seat Reservation Event Publisher
座位預訂事件發布器 - 負責發送座位預訂相關的領域事件

職責：
- 發送座位預訂成功事件
- 發送座位預訂失敗事件
- 封裝 Kafka 發布邏輯
"""

import attrs
from datetime import datetime, timezone
from typing import List

from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.event_publisher import publish_domain_event
from src.platform.message_queue.kafka_constant_builder import KafkaTopicBuilder
from src.service.ticketing.app.interface.i_seat_reservation_event_publisher import (
    ISeatReservationEventPublisher,
)


@attrs.define
class SeatsReservedEvent:
    """座位預訂成功事件"""

    booking_id: int
    buyer_id: int
    event_id: int  # Added: event_id is required for ticketing consumer
    reserved_seats: List[str]
    total_price: int
    ticket_details: List[dict]  # Required: contains seat_id and price
    status: str = 'seats_reserved'
    occurred_at: datetime = attrs.Factory(lambda: datetime.now(timezone.utc))

    @property
    def aggregate_id(self) -> int:
        return self.booking_id


@attrs.define
class SeatReservationFailedEvent:
    """座位預訂失敗事件"""

    booking_id: int
    buyer_id: int
    event_id: int  # Added: event_id is required for ticketing consumer
    error_message: str
    status: str = 'seat_reservation_failed'
    occurred_at: datetime = attrs.Factory(lambda: datetime.now(timezone.utc))

    @property
    def aggregate_id(self) -> int:
        return self.booking_id


class SeatReservationEventPublisher(ISeatReservationEventPublisher):
    """座位預訂事件發布器實作"""

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
        """發送座位預訂成功事件"""
        event = SeatsReservedEvent(
            booking_id=booking_id,
            buyer_id=buyer_id,
            event_id=event_id,  # Pass event_id to event
            reserved_seats=reserved_seats,
            total_price=total_price,
            ticket_details=ticket_details,
        )

        await publish_domain_event(
            event=event,
            topic=KafkaTopicBuilder.update_booking_status_to_pending_payment_and_ticket_status_to_reserved_in_postgresql(
                event_id=event_id
            ),
            partition_key=str(booking_id),
        )

        Logger.base.info(
            '\033[94m✅ [SEAT-RESERVATION Publisher] SeatsReserved 事件發送完成！\033[0m'
        )

    async def publish_reservation_failed(
        self,
        *,
        booking_id: int,
        buyer_id: int,
        error_message: str,
        event_id: int,
    ) -> None:
        """發送座位預訂失敗事件"""
        event = SeatReservationFailedEvent(
            booking_id=booking_id,
            buyer_id=buyer_id,
            event_id=event_id,  # Pass event_id to event
            error_message=error_message,
        )

        await publish_domain_event(
            event=event,
            topic=KafkaTopicBuilder.update_booking_status_to_failed(event_id=event_id),
            partition_key=str(booking_id),
        )

        Logger.base.info(
            '\033[91m❌ [SEAT-RESERVATION Publisher] ReservationFailed 事件發送完成\033[0m'
        )
