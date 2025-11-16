"""
Seat Reservation Event Publisher

Responsible for publishing seat reservation-related domain events.

Responsibilities:
- Publish seat reservation success events
- Publish seat reservation failure events
- Encapsulate Kafka publishing logic
"""

import attrs
from datetime import datetime, timezone
from typing import List

from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.event_publisher import publish_domain_event
from src.platform.message_queue.kafka_constant_builder import KafkaTopicBuilder
from src.service.seat_reservation.app.interface.i_seat_reservation_event_publisher import (
    ISeatReservationEventPublisher,
)


@attrs.define
class SeatsReservedEvent:
    """Seat reservation success event"""

    booking_id: str
    buyer_id: int
    event_id: int
    section: str
    subsection: int
    seat_selection_mode: str
    reserved_seats: List[str]
    total_price: int
    # Subsection stats from Kvrocks (for SSE broadcasting to frontend)
    # Check subsection_stats['available'] == 0 to know if subsection is sold out
    subsection_stats: dict[str, int] = attrs.Factory(
        dict
    )  # {'available': 95, 'reserved': 5, 'sold': 0, 'total': 100}
    # Event-level stats from Kvrocks (for SSE broadcasting to frontend)
    # Check event_stats['available'] == 0 to know if entire event is sold out
    event_stats: dict[str, int] = attrs.Factory(
        dict
    )  # {'available': 49950, 'reserved': 50, 'sold': 0, 'total': 50000}
    # Note: event_state removed - cache updates now via Redis Pub/Sub, not Kafka
    status: str = 'seats_reserved'
    occurred_at: datetime = attrs.Factory(lambda: datetime.now(timezone.utc))

    @property
    def aggregate_id(self) -> str:
        return self.booking_id


@attrs.define
class SeatReservationFailedEvent:
    """Seat reservation failure event - includes full booking info for direct FAILED booking creation"""

    booking_id: str
    buyer_id: int
    event_id: int
    section: str
    subsection: int
    quantity: int
    seat_selection_mode: str
    seat_positions: List[str]
    error_message: str
    status: str = 'seat_reservation_failed'
    occurred_at: datetime = attrs.Factory(lambda: datetime.now(timezone.utc))

    @property
    def aggregate_id(self) -> str:
        return self.booking_id


class SeatReservationEventPublisher(ISeatReservationEventPublisher):
    """Seat reservation event publisher implementation"""

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
        """Publish seat reservation success event (cache updates via Redis Pub/Sub separately)"""
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
        """Publish seat reservation failure event with full booking info"""
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
