"""
Booking Reservation Event Publisher Implementation

Kafka-based implementation that publishes events from Booking Service to Reservation Service.
"""

from opentelemetry import trace

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
    Uses section-subsection as partition key to ensure sequential processing.
    """

    def __init__(self) -> None:
        self.tracer = trace.get_tracer(__name__)

    @Logger.io
    async def publish_reservation_request(self, *, event: ReservationRequestEvent) -> None:
        """
        Publish reservation request to Reservation Service.

        Uses booking_to_reservation_reserve_seats topic.
        Partition key: {event_id}:{section}-{subsection} for sequential processing.
        """
        topic = KafkaTopicBuilder.booking_to_reservation_reserve_seats(event_id=event.event_id)

        # Use section-subsection as partition key to ensure all reservations
        # for the same section are processed sequentially by the same consumer
        partition_key = f'{event.event_id}:{event.section}-{event.subsection}'

        Logger.base.info(
            f'\033[94m📤 [BOOKING→RESERVATION] Publishing ReservationRequest '
            f'to Topic: {topic}\033[0m'
        )
        Logger.base.info(
            f'\033[94m📦 [BOOKING→RESERVATION] Event: booking_id={event.booking_id}, '
            f'event_id={event.event_id}, section={event.section}-{event.subsection}, '
            f'qty={event.quantity}, mode={event.seat_selection_mode}, '
            f'partition_key={partition_key}\033[0m'
        )

        await publish_domain_event(
            event=event,
            topic=topic,
            partition_key=partition_key,
        )

        Logger.base.info(
            '\033[94m✅ [BOOKING→RESERVATION] ReservationRequest published successfully\033[0m'
        )
