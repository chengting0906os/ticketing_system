"""
Booking Event Publisher Implementation

Concrete adapter that implements IBookingEventPublisher using confluent-kafka.
Handles infrastructure concerns like topic naming and event serialization.

Uses unified topic (ticket-command-request) with message_type header for routing:
- BookingCreatedDomainEvent: Reserve seats
- BookingCancelledEvent: Release seats
"""

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.event_publisher import publish_domain_event
from src.platform.message_queue.kafka_constant_builder import KafkaTopicBuilder
from src.service.ticketing.app.interface.i_booking_event_publisher import IBookingEventPublisher
from src.service.ticketing.domain.domain_event.booking_domain_event import (
    BookingCancelledEvent,
    BookingCreatedDomainEvent,
)


class BookingEventPublisherImpl(IBookingEventPublisher):
    """Kafka-based implementation of booking event publisher.

    All events published to unified topic (ticket-command-request) with
    message_type header for consumer routing.
    """

    @staticmethod
    def _calculate_partition(section: str, subsection: int) -> int:
        """Calculate Kafka partition from section/subsection"""
        section_index = ord(section.upper()) - ord('A')
        global_index = section_index * settings.SUBSECTIONS_PER_SECTION + (subsection - 1)
        return global_index % settings.KAFKA_TOTAL_PARTITIONS

    @Logger.io
    async def publish_booking_created(self, *, event: BookingCreatedDomainEvent) -> None:
        """Publish booking created event (reserve seats)."""
        topic = KafkaTopicBuilder.ticket_command_request(event_id=event.event_id)
        partition = self._calculate_partition(event.section, event.subsection)
        await publish_domain_event(
            event=event,
            topic=topic,
            partition=partition,
        )

    @Logger.io
    async def publish_booking_cancelled(self, *, event: BookingCancelledEvent) -> None:
        """Publish booking cancelled event (release seats)."""
        topic = KafkaTopicBuilder.ticket_command_request(event_id=event.event_id)
        partition = self._calculate_partition(event.section, event.subsection)
        await publish_domain_event(
            event=event,
            topic=topic,
            partition=partition,
        )
