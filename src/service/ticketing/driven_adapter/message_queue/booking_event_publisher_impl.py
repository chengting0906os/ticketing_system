"""
Booking Event Publisher Implementation

Concrete adapter that implements IBookingEventPublisher using Kafka/Quix Streams.
Handles infrastructure concerns like topic naming and event serialization.
"""

from opentelemetry import trace

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
    - Partition key strategy (using booking_id)
    - Event serialization (delegated to publish_domain_event)
    """

    def __init__(self):
        self.tracer = trace.get_tracer(__name__)

    @Logger.io
    async def publish_booking_created(self, *, event: BookingCreatedDomainEvent) -> None:
        """Publish BookingCreated event to ticket reservation topic"""
        topic = KafkaTopicBuilder.ticket_reserving_request_to_reserved_in_kvrocks(
            event_id=event.event_id
        )

        # Use section-subsection as partition key to ensure all reservations
        # for the same section are processed sequentially by the same consumer
        # This eliminates race conditions without needing Lua scripts
        partition_key = f'{event.event_id}:{event.section}-{event.subsection}'

        Logger.base.info(
            f'\033[92m📤 [BOOKING Publisher] Publishing BookingCreated to Topic: {topic}\033[0m'
        )
        Logger.base.info(
            f'\033[92m📦 [BOOKING Publisher] Event content: event_id={event.event_id}, '
            f'buyer_id={event.buyer_id}, seat_mode={event.seat_selection_mode}, '
            f'partition_key={partition_key}\033[0m'
        )

        await publish_domain_event(
            event=event,
            topic=topic,
            partition_key=partition_key,
        )

        Logger.base.info(
            '\033[92m✅ [BOOKING Publisher] BookingCreated event published successfully\033[0m'
        )

    @Logger.io
    async def publish_booking_paid(self, *, event: BookingPaidEvent) -> None:
        """Publish BookingPaidEvent to ticket completion topic"""
        # pyrefly: ignore  # missing-attribute
        topic = KafkaTopicBuilder.ticket_reserved_to_paid(event_id=event.event_id)

        Logger.base.info(
            f'💳 [PAYMENT Publisher] Publishing BookingPaidEvent for booking {event.booking_id} '
            f'with {len(event.ticket_ids)} tickets'
        )

        await publish_domain_event(
            event=event,
            topic=topic,
            partition_key=str(event.booking_id),
        )

        Logger.base.info(
            f'✅ [PAYMENT Publisher] BookingPaidEvent published successfully to {topic}'
        )

    @Logger.io
    async def publish_booking_cancelled(self, *, event: BookingCancelledEvent) -> None:
        """Publish BookingCancelledEvent to seat release topic"""
        # pyrefly: ignore  # missing-attribute
        topic = KafkaTopicBuilder.ticket_release_seats(event_id=event.event_id)

        Logger.base.info(
            f'🗑️ [CANCELLATION Publisher] Publishing BookingCancelledEvent for booking {event.booking_id}'
        )

        await publish_domain_event(
            event=event,
            topic=topic,
            partition_key=str(event.booking_id),
        )

        Logger.base.info(f'✅ [CANCELLATION Publisher] BookingCancelledEvent published to {topic}')
