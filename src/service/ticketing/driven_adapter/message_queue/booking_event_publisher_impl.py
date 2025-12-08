"""
Booking Event Publisher Implementation

Concrete adapter that implements IBookingEventPublisher using confluent-kafka.
Handles infrastructure concerns like topic naming and event serialization.
"""

from opentelemetry import trace

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.event_publisher import publish_domain_event
from src.platform.message_queue.kafka_constant_builder import KafkaTopicBuilder
from src.service.ticketing.app.interface.i_booking_event_publisher import IBookingEventPublisher
from src.service.ticketing.domain.domain_event.booking_domain_event import (
    BookingCancelledEvent,
    BookingCreatedDomainEvent,
    BookingPaidEvent,
)


class BookingEventPublisherImpl(IBookingEventPublisher):
    """
    Kafka-based implementation of booking event publisher.

    Encapsulates:
    - Topic naming strategy (using KafkaTopicBuilder)
    - Partition key strategy (explicit partition assignment for even distribution)
    - Event serialization (delegated to publish_domain_event)
    """

    def __init__(self) -> None:
        self.tracer = trace.get_tracer(__name__)
        self.total_partitions = settings.KAFKA_TOTAL_PARTITIONS

    def _calculate_partition(
        self, *, section: str, subsection: int, subsections_per_section: int
    ) -> int:
        section_index = ord(section.upper()) - ord('A')
        global_index = section_index * subsections_per_section + (subsection - 1)
        return global_index % self.total_partitions

    @Logger.io
    async def publish_booking_created(self, *, event: BookingCreatedDomainEvent) -> None:
        # NOTE: booking-service was removed, publish directly to reservation-service
        topic = KafkaTopicBuilder.booking_to_reservation_reserve_seats(event_id=event.event_id)

        # Calculate partition explicitly to avoid hash collision hotspots
        partition = self._calculate_partition(
            section=event.section,
            subsection=event.subsection,
            subsections_per_section=settings.SUBSECTIONS_PER_SECTION,
        )

        await publish_domain_event(
            event=event,
            topic=topic,
            partition=partition,
        )

    @Logger.io
    async def publish_booking_paid(self, *, event: BookingPaidEvent) -> None:
        topic = KafkaTopicBuilder.finalize_ticket_status_to_paid_in_kvrocks(event_id=event.event_id)

        partition = self._calculate_partition(
            section=event.section,
            subsection=event.subsection,
            subsections_per_section=settings.SUBSECTIONS_PER_SECTION,
        )

        await publish_domain_event(
            event=event,
            topic=topic,
            partition=partition,
        )

    @Logger.io
    async def publish_booking_cancelled(self, *, event: BookingCancelledEvent) -> None:
        topic = KafkaTopicBuilder.release_ticket_status_to_available_in_kvrocks(
            event_id=event.event_id
        )

        partition = self._calculate_partition(
            section=event.section,
            subsection=event.subsection,
            subsections_per_section=settings.SUBSECTIONS_PER_SECTION,
        )

        await publish_domain_event(
            event=event,
            topic=topic,
            partition=partition,
        )
