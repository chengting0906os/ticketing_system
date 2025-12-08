"""
Booking Reservation Event Publisher Implementation

Kafka-based implementation that publishes events from Booking Service to Reservation Service.
"""

from opentelemetry import trace

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.event_publisher import publish_domain_event
from src.platform.message_queue.kafka_constant_builder import KafkaTopicBuilder
from src.service.booking.app.interface.i_booking_reservation_event_publisher import (
    IBookingReservationEventPublisher,
)
from src.service.booking.domain.domain_event.reservation_request_event import (
    ReservationRequestEvent,
)


class BookingReservationEventPublisherImpl(IBookingReservationEventPublisher):
    """
    Kafka-based implementation of booking-to-reservation event publisher.

    Publishes ReservationRequestEvent to Reservation Service via Kafka.
    Uses explicit partition assignment for even distribution across partitions.
    """

    def __init__(self) -> None:
        self.tracer = trace.get_tracer(__name__)
        self.total_partitions = settings.KAFKA_TOTAL_PARTITIONS

    def _calculate_partition(
        self, *, section: str, subsection: int, subsections_per_section: int
    ) -> int:
        """
        Calculate partition number based on section and subsection.

        Maps subsections evenly across partitions:
        - For 100 subsections (10 sections × 10): 1:1 mapping to 100 partitions
        - For 400 subsections (10 sections × 40): 4 subsections per partition


        Returns:
            Partition number (0 to total_partitions-1)
        """
        section_index = ord(section.upper()) - ord('A')
        global_index = section_index * subsections_per_section + (subsection - 1)
        return global_index % self.total_partitions

    @Logger.io
    async def publish_reservation_request(self, *, event: ReservationRequestEvent) -> None:
        """
        Publish reservation request to Reservation Service.

        Uses booking_to_reservation_reserve_seats topic.
        Explicitly assigns partition based on section-subsection for even distribution.
        """
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
