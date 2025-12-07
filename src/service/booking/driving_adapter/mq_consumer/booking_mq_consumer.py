"""
Booking Service Consumer

Consumes booking creation requests from Ticketing Service.
Responsibilities:
1. Receive booking request from Ticketing
2. Create booking metadata in Kvrocks
3. Publish reservation request to Reservation Service

Design Principle: No decision logic - receive and forward.

Uses confluent-kafka for high-performance concurrent message processing.
"""

import os
from typing import Any, Callable, Dict, Optional

from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.base_kafka_consumer import BaseKafkaConsumer
from src.platform.message_queue.kafka_constant_builder import (
    KafkaConsumerGroupBuilder,
    KafkaTopicBuilder,
)
from src.platform.message_queue.proto import domain_event_pb2 as pb
from src.service.booking.app.command.create_booking_metadata_use_case import (
    CreateBookingMetadataUseCase,
)
from src.service.booking.driven_adapter.message_queue.booking_reservation_event_publisher_impl import (
    BookingReservationEventPublisherImpl,
)
from src.service.booking.driven_adapter.repo.booking_metadata_handler_impl import (
    BookingMetadataHandlerImpl,
)
from src.service.shared_kernel.domain.value_object import SubsectionConfig


class BookingConsumer(BaseKafkaConsumer):
    """
    Booking Service Consumer

    Listens to:
    1. ticketing_to_booking_create_metadata - Booking requests from Ticketing

    Flow:
    Ticketing -> [Kafka] -> Booking Consumer -> Create metadata -> [Kafka] -> Reservation
    """

    # Override base class settings for booking service
    MAX_WORKERS = 8  # More workers for higher throughput

    def __init__(self) -> None:
        event_id = int(os.getenv('EVENT_ID', '1'))
        consumer_group_id = os.getenv(
            'CONSUMER_GROUP_ID',
            KafkaConsumerGroupBuilder.booking_service(event_id=event_id),
        )
        dlq_topic = KafkaTopicBuilder.booking_dlq(event_id=event_id)

        super().__init__(
            service_name='BOOKING',
            consumer_group_id=consumer_group_id,
            event_id=event_id,
            dlq_topic=dlq_topic,
        )

        # Use case (lazy initialization)
        self.create_booking_metadata_use_case: Optional[CreateBookingMetadataUseCase] = None

        # Topic name
        self.create_metadata_topic = KafkaTopicBuilder.ticketing_to_booking_create_metadata(
            event_id=event_id
        )

    def _initialize_dependencies(self) -> None:
        """Initialize use case with dependencies"""
        booking_metadata_handler = BookingMetadataHandlerImpl()
        event_publisher = BookingReservationEventPublisherImpl()

        self.create_booking_metadata_use_case = CreateBookingMetadataUseCase(
            booking_metadata_handler=booking_metadata_handler,
            event_publisher=event_publisher,
        )

    def _get_topic_handlers(self) -> Dict[str, tuple[type, Callable[[Dict], Any]]]:
        """Return topic to handler mapping"""
        return {
            self.create_metadata_topic: (
                pb.BookingCreatedDomainEvent,
                self._handle_create_metadata,
            ),
        }

    def _handle_create_metadata(self, message: Dict) -> Dict:
        """
        Process booking creation request from Ticketing Service.

        Flow:
        1. Parse message (Protobuf -> dict via deserializer)
        2. Call CreateBookingMetadataUseCase
        3. Use case saves to Kvrocks and publishes to Reservation
        """
        booking_id = message.get('booking_id', 'unknown')

        Logger.base.info(
            f'\033[93m[BOOKING-{self.instance_id}] Processing: booking_id={booking_id}\033[0m'
        )

        # Execute use case via portal (async -> sync bridge)
        result = self.portal.call(self._handle_create_metadata_async, message)

        return {'success': True, 'result': result}

    async def _handle_create_metadata_async(self, event_data: Dict) -> bool:
        """Handle booking metadata creation asynchronously"""
        booking_id = event_data.get('booking_id')
        buyer_id = event_data.get('buyer_id')
        event_id = event_data.get('event_id')

        if not all([booking_id, buyer_id, event_id]):
            raise ValueError('Missing required fields: booking_id, buyer_id, or event_id')

        # Type narrowing after validation
        assert buyer_id is not None
        assert event_id is not None

        # Extract config (optional - may be None if subsection doesn't exist)
        config_data = event_data.get('config')
        config = None
        if config_data:
            # Use .get() for safe access - MessageToDict omits fields with default values
            config = SubsectionConfig(
                rows=config_data.get('rows', 0),
                cols=config_data.get('cols', 0),
                price=config_data.get('price', 0),
            )

        await self.create_booking_metadata_use_case.execute(
            booking_id=str(booking_id),
            buyer_id=int(buyer_id),
            event_id=int(event_id),
            section=event_data['section'],
            subsection=int(event_data['subsection']),
            quantity=int(event_data['quantity']),
            seat_selection_mode=event_data['seat_selection_mode'],
            seat_positions=event_data.get('seat_positions', []),
            config=config,
        )

        return True
