"""
Booking Event Publisher Implementation

Concrete adapter that implements IBookingEventPublisher using Kafka/Quix Streams.
Handles infrastructure concerns like topic naming and event serialization.
"""

from opentelemetry import trace

from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.event_publisher import publish_domain_event
from src.platform.message_queue.kafka_constant_builder import KafkaTopicBuilder
from src.platform.message_queue.subsection_based_partition_strategy import (
    SubSectionBasedPartitionStrategy,
)
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
    - Partition key strategy (using section-subsection for ordering guarantee)
    - Event serialization (delegated to publish_domain_event)
    """

    def __init__(self):
        self.tracer = trace.get_tracer(__name__)
        self.partition_strategy = SubSectionBasedPartitionStrategy()

    async def publish_booking_created(self, *, event: BookingCreatedDomainEvent) -> None:
        """Publish BookingCreated event to ticket reservation topic"""
        with self.tracer.start_as_current_span(
            'kafka.publish_booking_created',
            attributes={
                'booking_id': str(event.booking_id),
                'event_id': str(event.event_id),
                'buyer_id': str(event.buyer_id),
                'seat_selection_mode': event.seat_selection_mode,
                'quantity': event.quantity,
            },
        ):
            topic = KafkaTopicBuilder.ticket_reserving_request_to_reserved_in_kvrocks(
                event_id=event.event_id
            )

            # Use section-subsection based partition key for ordering guarantee
            # All bookings for same subsection go to same partition → sequential processing
            partition_key = self.partition_strategy.generate_partition_key(
                section=event.section,
                subsection=event.subsection,
                row=0,  # Not used for partition calculation
                seat=0,  # Not used for partition calculation
                event_id=event.event_id,
            )

            Logger.base.info(
                f'\033[92m📤 [BOOKING Publisher] 發送 BookingCreated 到 Topic: {topic}\033[0m'
            )
            Logger.base.info(
                f'\033[92m📦 [BOOKING Publisher] 事件內容: event_id={event.event_id}, '
                f'buyer_id={event.buyer_id}, seat_mode={event.seat_selection_mode}, '
                f'partition_key={partition_key}\033[0m'
            )

            await publish_domain_event(
                event=event,
                topic=topic,
                partition_key=partition_key,
            )

            Logger.base.info('\033[92m✅ [BOOKING Publisher] BookingCreated 事件發送完成！\033[0m')

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
            force_flush=True,  # 付款事件需立即確認
        )

        Logger.base.info(
            f'✅ [PAYMENT Publisher] BookingPaidEvent published successfully to {topic}'
        )

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
