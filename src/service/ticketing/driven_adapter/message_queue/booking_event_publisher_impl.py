"""
Booking Event Publisher Implementation

Concrete adapter that implements IBookingEventPublisher using Kafka/Quix Streams.
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

    def _calculate_partition_by_section_and_subsection(
        self, *, section: str, subsection: int, subsections_per_section: int = 10
    ) -> int:
        """
        Calculate partition number based on section and subsection.

        Maps subsections evenly across partitions to avoid hotspots.
        """
        section_index = ord(section.upper()) - ord('A')
        global_index = section_index * subsections_per_section + (subsection - 1)
        return global_index % self.total_partitions

    @Logger.io
    async def publish_booking_created(self, *, event: BookingCreatedDomainEvent) -> None:
        """Publish BookingCreated event directly to Reservation Service"""
        topic = KafkaTopicBuilder.ticketing_to_reservation_reserve_seats(event_id=event.event_id)

        # Calculate partition explicitly to avoid hash collision hotspots
        partition = self._calculate_partition_by_section_and_subsection(
            section=event.section,
            subsection=event.subsection,
        )

        # Keep partition_key for message ordering within partition
        partition_key = f'{event.event_id}:{event.section}-{event.subsection}'

        Logger.base.info(
            f'\033[92m📤 [TICKETING→RESERVATION] Publishing BookingCreated to Topic: {topic} Partition: {partition}\033[0m'
        )

        await publish_domain_event(
            event=event,
            topic=topic,
            partition_key=partition_key,
            partition=partition,
        )

        Logger.base.info(
            '\033[92m✅ [TICKETING→RESERVATION] BookingCreated event published successfully\033[0m'
        )

    @Logger.io
    async def publish_booking_paid(self, *, event: BookingPaidEvent) -> None:
        """Publish BookingPaidEvent to finalize payment in Reservation Service"""
        topic = KafkaTopicBuilder.ticket_reserved_to_paid(event_id=event.event_id)
        partition = self._calculate_partition_by_section_and_subsection(
            section=event.section,
            subsection=event.subsection,
        )

        Logger.base.info(
            f'💳 [TICKETING→RESERVATION] Publishing BookingPaidEvent for booking {event.booking_id}'
        )

        await publish_domain_event(
            event=event,
            topic=topic,
            partition_key=str(event.booking_id),
            partition=partition,
        )

        Logger.base.info(f'✅ [TICKETING→RESERVATION] BookingPaidEvent published to {topic}')

    @Logger.io
    async def publish_booking_cancelled(self, *, event: BookingCancelledEvent) -> None:
        """Publish BookingCancelledEvent to release seats in Reservation Service"""
        topic = KafkaTopicBuilder.ticket_release_seats(event_id=event.event_id)
        partition = self._calculate_partition_by_section_and_subsection(
            section=event.section,
            subsection=event.subsection,
        )

        await publish_domain_event(
            event=event,
            topic=topic,
            partition_key=str(event.booking_id),
            partition=partition,
        )

        Logger.base.info(f'✅ [TICKETING→RESERVATION] BookingCancelledEvent published to {topic}')
