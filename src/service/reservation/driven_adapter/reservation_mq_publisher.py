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

from src.platform.config.core_setting import settings
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
    def __init__(self) -> None:
        self.total_partitions = settings.KAFKA_TOTAL_PARTITIONS

    def _calculate_partition(
        self, *, section: str, subsection: int, subsections_per_section: int
    ) -> int:
        section_index = ord(section.upper()) - ord('A')
        global_index = section_index * subsections_per_section + (subsection - 1)
        return global_index % self.total_partitions

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

        partition = self._calculate_partition(
            section=section,
            subsection=subsection,
            subsections_per_section=settings.SUBSECTIONS_PER_SECTION,
        )

        await publish_domain_event(
            event=event,
            topic=KafkaTopicBuilder.update_booking_status_to_pending_payment_and_ticket_status_to_reserved_in_postgresql(
                event_id=event_id
            ),
            partition=partition,
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

        partition = self._calculate_partition(
            section=section,
            subsection=subsection,
            subsections_per_section=settings.SUBSECTIONS_PER_SECTION,
        )

        await publish_domain_event(
            event=event,
            topic=KafkaTopicBuilder.update_booking_status_to_failed(event_id=event_id),
            partition=partition,
        )
