"""
Booking Service Consumer

Consumes booking creation requests from Ticketing Service.
Responsibilities:
1. Receive booking request from Ticketing
2. Create booking metadata in Kvrocks
3. Publish reservation request to Reservation Service

Design Principle: No decision logic - receive and forward.
"""

import os
import time
from typing import TYPE_CHECKING, Dict, Literal, Optional

from opentelemetry import trace
import orjson
from quixstreams import Application

if TYPE_CHECKING:
    from anyio.from_thread import BlockingPortal

from src.platform.config.core_setting import KafkaConfig, settings
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.kafka_constant_builder import (
    KafkaConsumerGroupBuilder,
    KafkaTopicBuilder,
)
from src.platform.observability.tracing import extract_trace_context
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


class BookingConsumer:
    """
    Booking Service Consumer

    Listens to:
    1. ticketing_to_booking_create_metadata - Booking requests from Ticketing

    Flow:
    Ticketing → [Kafka] → Booking Consumer → Create metadata → [Kafka] → Reservation
    """

    PROCESSING_GUARANTEE: Literal['at-least-once', 'exactly-once'] = 'at-least-once'

    def __init__(self) -> None:
        self.event_id = int(os.getenv('EVENT_ID', '1'))
        self.consumer_instance_id = settings.KAFKA_CONSUMER_INSTANCE_ID
        self.instance_id = self.consumer_instance_id
        self.consumer_group_id = os.getenv(
            'CONSUMER_GROUP_ID',
            KafkaConsumerGroupBuilder.booking_service(event_id=self.event_id),
        )

        self.kafka_config = KafkaConfig(event_id=self.event_id, service='booking')
        self.kafka_app: Optional[Application] = None
        self.running = False
        self.portal: Optional['BlockingPortal'] = None
        self.tracer = trace.get_tracer(__name__)

        # DLQ configuration
        self.dlq_topic = KafkaTopicBuilder.booking_dlq(event_id=self.event_id)

        # Use case (lazy initialization)
        self.create_booking_metadata_use_case: Optional[CreateBookingMetadataUseCase] = None

    def set_portal(self, portal: 'BlockingPortal') -> None:
        """Set BlockingPortal for calling async functions from sync code"""
        self.portal = portal

    def _on_processing_error(self, exc: Exception, row: object, _logger: object) -> bool:
        """
        Quix Streams error handling callback

        Returns:
            True: Send to DLQ and commit offset
        """
        Logger.base.error(f'❌ [BOOKING-ERROR] Processing failed, sending to DLQ: {exc}')

        if row and hasattr(row, 'value'):
            self._send_to_dlq(
                message=row.value,
                original_topic='ticketing_to_booking_create_metadata',
                error=str(exc),
                retry_count=0,
            )

        return True

    def _create_kafka_app(self) -> Application:
        app = Application(
            broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=self.consumer_group_id,
            processing_guarantee=self.PROCESSING_GUARANTEE,
            commit_interval=0.2,
            producer_extra_config=self.kafka_config.producer_config,
            consumer_extra_config=self.kafka_config.consumer_config,
            on_processing_error=self._on_processing_error,
        )

        Logger.base.info(
            f'📦 [BOOKING] Created Kafka app\n'
            f'   👥 Group: {self.consumer_group_id}\n'
            f'   🎫 Event: {self.event_id}\n'
            f'   🔒 Processing: {self.PROCESSING_GUARANTEE}'
        )
        return app

    def _setup_topics(self) -> None:
        if not self.kafka_app:
            self.kafka_app = self._create_kafka_app()

        # Subscribe to ticketing_to_booking topic
        topic_name = KafkaTopicBuilder.ticketing_to_booking_create_metadata(
            event_id=self.event_id
        )

        topic = self.kafka_app.topic(
            name=topic_name,
            key_serializer='str',
            value_serializer='json',
        )

        self.kafka_app.dataframe(topic=topic).apply(
            self._process_create_booking_metadata, stateful=False
        )

        Logger.base.info(f'   ✓ Subscribed to: {topic_name}')
        Logger.base.info('✅ [BOOKING] Topics configured')

    def _send_to_dlq(
        self, *, message: Dict, original_topic: str, error: str, retry_count: int
    ) -> None:
        if not self.kafka_app:
            Logger.base.error('❌ [DLQ] Kafka app not initialized')
            return

        try:
            dlq_message = {
                'original_message': message,
                'original_topic': original_topic,
                'error': error,
                'retry_count': retry_count,
                'timestamp': time.time(),
                'instance_id': self.instance_id,
            }

            serialized_message = orjson.dumps(dlq_message)

            with self.kafka_app.get_producer() as producer:
                producer.produce(
                    topic=self.dlq_topic,
                    key=str(message.get('booking_id', 'unknown')),
                    value=serialized_message,
                )

            Logger.base.warning(
                f'📮 [DLQ] Sent to DLQ: {message.get("booking_id")} - {error}'
            )

        except Exception as e:
            Logger.base.error(f'❌ [DLQ] Failed to send to DLQ: {e}')

    def _process_create_booking_metadata(
        self, message: Dict, key: object = None, context: object = None
    ) -> Dict:
        """
        Process booking creation request from Ticketing Service.

        Flow:
        1. Parse message
        2. Call CreateBookingMetadataUseCase
        3. Use case saves to Kvrocks and publishes to Reservation
        """
        # Extract trace context
        trace_headers = message.get('_trace_headers', {})
        if trace_headers:
            extract_trace_context(headers=trace_headers)

        partition_info = ''
        if hasattr(context, 'partition'):
            partition_info = f' | partition={context.partition}'

        booking_id = message.get('booking_id', 'unknown')

        with self.tracer.start_as_current_span(
            'consumer.create_booking_metadata',
            attributes={
                'messaging.system': 'kafka',
                'messaging.operation': 'process',
                'booking.id': booking_id,
            },
        ):
            Logger.base.info(
                f'\033[93m📦 [BOOKING-{self.instance_id}] Processing: '
                f'booking_id={booking_id}{partition_info}\033[0m'
            )

            # Execute use case (exceptions will be caught by on_processing_error)
            result = self.portal.call(self._handle_create_metadata_async, message)  # type: ignore

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

        # Extract config (required - fail fast if missing)
        config_data = event_data.get('config')
        config = None
        if config_data:
            config = SubsectionConfig(
                rows=config_data['rows'],
                cols=config_data['cols'],
                price=config_data['price'],
            )

        await self.create_booking_metadata_use_case.execute(  # type: ignore
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

    def _initialize_use_case(self) -> None:
        """Initialize use case with dependencies"""
        booking_metadata_handler = BookingMetadataHandlerImpl()
        event_publisher = BookingReservationEventPublisherImpl()

        self.create_booking_metadata_use_case = CreateBookingMetadataUseCase(
            booking_metadata_handler=booking_metadata_handler,
            event_publisher=event_publisher,
        )

    def start(self) -> None:
        """Start service with retry mechanism"""
        max_retries = 5
        retry_delay = 2

        for attempt in range(1, max_retries + 1):
            try:
                # Initialize use case
                self._initialize_use_case()

                # Setup Kafka
                self._setup_topics()

                Logger.base.info(
                    f'🚀 [BOOKING-{self.instance_id}] Started\n'
                    f'   📊 Event: {self.event_id}\n'
                    f'   👥 Group: {self.consumer_group_id}\n'
                    f'   🔒 Processing: {self.PROCESSING_GUARANTEE}'
                )

                self.running = True
                if self.kafka_app:
                    self.kafka_app.run()
                    break

            except Exception as e:
                error_msg = str(e)

                if 'UNKNOWN_TOPIC_OR_PART' in error_msg and attempt < max_retries:
                    Logger.base.warning(
                        f'⚠️ [BOOKING] Attempt {attempt}/{max_retries} failed: '
                        f'Topic metadata not ready, retrying in {retry_delay}s...'
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    self.kafka_app = None
                    continue
                else:
                    Logger.base.error(f'❌ [BOOKING] Start failed: {e}')
                    raise

    def stop(self) -> None:
        """Stop service"""
        if not self.running:
            return

        self.running = False

        if self.kafka_app:
            try:
                Logger.base.info('🛑 Stopping Kafka app...')
                self.kafka_app = None
            except Exception as e:
                Logger.base.warning(f'⚠️ Stop error: {e}')

        Logger.base.info('🛑 [BOOKING] Consumer stopped')
