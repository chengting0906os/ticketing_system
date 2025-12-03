"""
Seat Reservation Event Publisher

Responsible for publishing seat reservation-related domain events.

Responsibilities:
- Publish seat reservation success events
- Publish seat reservation failure events
- Encapsulate Kafka publishing logic
"""

from datetime import datetime, timezone
from typing import List

import attrs

from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.event_publisher import publish_domain_event
from src.platform.message_queue.kafka_constant_builder import KafkaTopicBuilder
from src.service.reservation.app.interface.i_reservation_event_publisher import (
    ISeatReservationEventPublisher,
)


@attrs.define
class SeatsReservedEvent:
    booking_id: str
    buyer_id: int
    event_id: int
    section: str
    subsection: int
    seat_selection_mode: str
    reserved_seats: List[str]
    total_price: int
    subsection_stats: dict[str, int] = attrs.Factory(
        dict
    )  # {'available': 95, 'reserved': 5, 'sold': 0, 'total': 100}
    event_stats: dict[str, int] = attrs.Factory(
        dict
    )  # {'available': 49950, 'reserved': 50, 'sold': 0, 'total': 50000}
    status: str = 'seats_reserved'
    occurred_at: datetime = attrs.Factory(lambda: datetime.now(timezone.utc))


@attrs.define
class SeatReservationFailedEvent:
    booking_id: str
    buyer_id: int
    event_id: int
    section: str
    subsection: int
    quantity: int
    seat_selection_mode: str
    seat_positions: List[str]
    error_message: str
    status: str = 'reservation_failed'
    occurred_at: datetime = attrs.Factory(lambda: datetime.now(timezone.utc))


class SeatReservationEventPublisher(ISeatReservationEventPublisher):
    async def publish_seats_reserved(
        self,
        *,
        booking_id: str,
        buyer_id: int,
        event_id: int,
        section: str,
        subsection: int,
        seat_selection_mode: str,
        reserved_seats: List[str],
        total_price: int,
        subsection_stats: dict[str, int],
        event_stats: dict[str, int],
    ) -> None:
        event = SeatsReservedEvent(
            booking_id=booking_id,
            buyer_id=buyer_id,
            event_id=event_id,
            section=section,
            subsection=subsection,
            seat_selection_mode=seat_selection_mode,
            reserved_seats=reserved_seats,
            total_price=total_price,
            subsection_stats=subsection_stats,
            event_stats=event_stats,
        )

        await publish_domain_event(
            event=event,
            topic=KafkaTopicBuilder.update_booking_status_to_pending_payment_and_ticket_status_to_reserved_in_postgresql(
                event_id=event_id
            ),
            partition_key=str(booking_id),
        )

        Logger.base.info(
            '\033[94m✅ [SEAT-RESERVATION Publisher] SeatsReserved event published successfully\033[0m'
        )

    async def publish_reservation_failed(
        self,
        *,
        booking_id: str,
        buyer_id: int,
        event_id: int,
        section: str,
        subsection: int,
        quantity: int,
        seat_selection_mode: str,
        seat_positions: List[str],
        error_message: str,
    ) -> None:
        event = SeatReservationFailedEvent(
            booking_id=booking_id,
            buyer_id=buyer_id,
            event_id=event_id,
            section=section,
            subsection=subsection,
            quantity=quantity,
            seat_selection_mode=seat_selection_mode,
            seat_positions=seat_positions,
            error_message=error_message,
        )

        await publish_domain_event(
            event=event,
            topic=KafkaTopicBuilder.update_booking_status_to_failed(event_id=event_id),
            partition_key=str(booking_id),
        )

        Logger.base.info(
            '\033[91m❌ [SEAT-RESERVATION Publisher] ReservationFailed event published\033[0m'
        )
