"""
Booking Service Consumer

Consumes booking creation requests from Ticketing Service.
Responsibilities:
1. Receive booking request from Ticketing
2. Create booking metadata in Kvrocks
3. Publish reservation request to Reservation Service

Design Principle: No decision logic - receive and forward.

Uses confluent-kafka experimental AIOConsumer for async message processing.
"""

import os
from typing import Any, Awaitable, Callable, Dict, Optional

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
    Booking Service Consumer - Async Message Handler

    Listens to 1 Topic:
    1. ticketing_to_booking_create_metadata - Create booking metadata requests

    Uses confluent-kafka AIOConsumer for async message processing.
    """

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
        self.create_metadata_topic = KafkaTopicBuilder.ticketing_to_booking_create_metadata(
            event_id=event_id
        )

    async def _initialize_dependencies(self) -> None:
        """Initialize use cases from dependencies."""
        booking_metadata_handler = BookingMetadataHandlerImpl()
        event_publisher = BookingReservationEventPublisherImpl()

        self.create_booking_metadata_use_case = CreateBookingMetadataUseCase(
            booking_metadata_handler=booking_metadata_handler,
            event_publisher=event_publisher,
        )

    def _get_topic_handlers(
        self,
    ) -> Dict[str, tuple[type, Callable[[Dict], Awaitable[Any]]]]:
        """Return topic to async handler mapping."""
        return {
            self.create_metadata_topic: (
                pb.BookingCreatedDomainEvent,
                self._handle_create_metadata,
            ),
        }

    # ========== Async Message Handlers ==========

    async def _handle_create_metadata(self, message: Dict) -> Dict:
        """
        Process booking creation request from Ticketing Service (async).

        Flow:
        1. Parse message (Protobuf -> dict via deserializer)
        2. Call CreateBookingMetadataUseCase
        3. Use case saves to Kvrocks and publishes to Reservation
        """
        booking_id = message.get('booking_id', 'unknown')

        Logger.base.info(
            f'\033[93m[BOOKING-{self.instance_id}] Processing: booking_id={booking_id}\033[0m'
        )

        await self._execute_create_metadata(message)
        return {'success': True}

    async def _execute_create_metadata(self, event_data: Dict) -> bool:
        """Execute the create metadata use case."""
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
