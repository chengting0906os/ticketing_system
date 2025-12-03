"""
Booking Service MQ Consumer - Unified PostgreSQL State Manager

Integrated Responsibilities (2 topics):
1. Booking + Ticket State Sync (Atomic Operation):
   - pending_payment_and_reserved: After successful seat reservation, simultaneously update Booking to PENDING_PAYMENT and Ticket to RESERVED

2. Booking Failure Handling:
   - failed: Update order status after seat reservation failure

Important:
- This consumer **only operates on PostgreSQL**, doesn't touch Kvrocks!
- Kvrocks state management is the responsibility of reservation_consumer
- Merged topics ensure atomicity of Booking and Ticket state updates

Features:
- Error Handling: Use Quix Streams callback to handle errors
- Dead Letter Queue: Failed messages sent to DLQ
"""

import os
import time
from typing import TYPE_CHECKING, Any, Dict, Literal, Optional

from anyio.from_thread import BlockingPortal
from opentelemetry import trace
import orjson
from quixstreams import Application
from uuid_utils import UUID


if TYPE_CHECKING:
    from anyio.from_thread import BlockingPortal

from quixstreams.models.serializers.protobuf import ProtobufDeserializer

from src.platform.config.core_setting import KafkaConfig, settings
from src.platform.event.i_in_memory_broadcaster import IInMemoryEventBroadcaster
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.kafka_constant_builder import (
    KafkaConsumerGroupBuilder,
    KafkaTopicBuilder,
)
from src.platform.message_queue.proto import domain_event_pb2 as pb
from src.platform.observability.tracing import extract_trace_context
from src.service.ticketing.app.command.update_booking_status_to_failed_use_case import (
    UpdateBookingToFailedUseCase,
)
from src.service.ticketing.app.command.update_booking_status_to_pending_payment_and_ticket_to_reserved_use_case import (
    UpdateBookingToPendingPaymentAndTicketToReservedUseCase,
)
from src.service.ticketing.driven_adapter.repo.booking_command_repo_impl import (
    BookingCommandRepoImpl,
)


class BookingMqConsumer:
    """
    Integrated Ticketing MQ Consumer (PostgreSQL State Management)

    Handles 2 topics:
    - Booking + Ticket atomic update (pending_payment + reserved)
    - Booking failure handling (failed)

    All PostgreSQL operations, stateless processing
    """

    PROCESSING_GUARANTEE: Literal['at-least-once', 'exactly-once'] = 'at-least-once'

    def __init__(
        self,
        *,
        event_broadcaster: IInMemoryEventBroadcaster,
    ) -> None:
        self.event_id = int(os.getenv('EVENT_ID', '1'))
        # Use consumer instance_id for consumer group identification
        self.consumer_instance_id = settings.KAFKA_CONSUMER_INSTANCE_ID
        # Alias for backward compatibility
        self.instance_id = self.consumer_instance_id
        self.consumer_group_id = os.getenv(
            'CONSUMER_GROUP_ID',
            KafkaConsumerGroupBuilder.ticketing_service(event_id=self.event_id),
        )

        # KafkaConfig now gets producer instance_id from settings directly (lazy evaluation)
        self.kafka_config = KafkaConfig(event_id=self.event_id, service='ticketing')
        self.kafka_app: Optional[Application] = None
        self.running = False
        self.portal: Optional['BlockingPortal'] = None
        self.event_broadcaster: IInMemoryEventBroadcaster = event_broadcaster
        self.tracer = trace.get_tracer(__name__)

        # DLQ configuration
        self.dlq_topic = KafkaTopicBuilder.ticketing_dlq(event_id=self.event_id)

        # Use cases (lazy initialization)
        self.update_booking_to_pending_payment_use_case: Any = None
        self.update_booking_to_failed_use_case: Any = None

    def set_portal(self, portal: 'BlockingPortal') -> None:
        """Set BlockingPortal for calling async functions from sync code"""
        self.portal = portal

    def _on_processing_error(self, exc: Exception, row: object, _logger: object) -> bool:
        """
        Quix Streams error handling callback

        Returns:
            True: Send to DLQ and commit offset
        """
        Logger.base.error(f'❌ [CONSUMER-ERROR] Processing failed, sending to DLQ: {exc}')

        # Send to DLQ to preserve failed messages
        if row and hasattr(row, 'value'):
            self._send_to_dlq(
                message=row.value,
                original_topic='unknown',
                error=str(exc),
                retry_count=0,
            )

        # Commit offset - message saved in DLQ
        return True

    @Logger.io
    def _create_kafka_app(self) -> Application:
        """Create Kafka application with At-Least-Once for lower latency"""
        app = Application(
            broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=self.consumer_group_id,
            processing_guarantee=self.PROCESSING_GUARANTEE,
            commit_interval=0.2,  # Commit every 200ms for high-throughput scenarios
            producer_extra_config=self.kafka_config.producer_config,
            consumer_extra_config=self.kafka_config.consumer_config,
            on_processing_error=self._on_processing_error,
        )

        Logger.base.info(
            f'🎫 [TICKETING] Created Kafka app\n'
            f'   👥 Group: {self.consumer_group_id}\n'
            f'   🎫 Event: {self.event_id}\n'
            f'   🔒 Processing: {self.PROCESSING_GUARANTEE}\n'
            f'   ⚠️ Error handling: enabled'
        )
        return app

    @Logger.io
    def _setup_topics(self) -> None:
        """Setup processing logic for 2 topics - Use Kafka transactions for Exactly Once"""
        if not self.kafka_app:
            self.kafka_app = self._create_kafka_app()

        # === Topic 1: SeatsReservedEvent (Protobuf) ===
        pending_topic = self.kafka_app.topic(
            name=KafkaTopicBuilder.update_booking_status_to_pending_payment_and_ticket_status_to_reserved_in_postgresql(
                event_id=self.event_id
            ),
            key_serializer='str',
            value_deserializer=ProtobufDeserializer(
                msg_type=pb.SeatsReservedEvent, preserving_proto_field_name=True
            ),
        )
        self.kafka_app.dataframe(topic=pending_topic).apply(
            self._process_pending_payment_and_reserved, stateful=False
        )
        # === Topic 2: SeatReservationFailedEvent (Protobuf) ===
        failed_topic = self.kafka_app.topic(
            name=KafkaTopicBuilder.update_booking_status_to_failed(event_id=self.event_id),
            key_serializer='str',
            value_deserializer=ProtobufDeserializer(
                msg_type=pb.SeatReservationFailedEvent, preserving_proto_field_name=True
            ),
        )
        self.kafka_app.dataframe(topic=failed_topic).apply(self._process_failed, stateful=False)
        Logger.base.info('✅ All topics configured (exactly once via Kafka transactions)')

    # ========== DLQ Helper ==========

    @Logger.io
    def _send_to_dlq(
        self, *, message: Dict, original_topic: str, error: str, retry_count: int
    ) -> None:
        """Send failed message to DLQ"""
        if not self.kafka_app:
            Logger.base.error('❌ [TICKETING-DLQ] Kafka app not initialized')
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

            # Send to DLQ (use booking_id as key to maintain order)
            serialized_message = orjson.dumps(dlq_message)
            with self.kafka_app.get_producer() as producer:
                producer.produce(
                    topic=self.dlq_topic,
                    key=str(message.get('booking_id', 'unknown')),
                    value=serialized_message,
                )

            Logger.base.warning(
                f'📮 [TICKETING-DLQ] Sent to DLQ: booking_id={message.get("booking_id")} '
                f'after {retry_count} retries, error: {error}'
            )

        except Exception as e:
            Logger.base.error(f'❌ [TICKETING-DLQ] Failed to send to DLQ: {e}')

    # ========== Message Handlers ==========

    @Logger.io
    def _process_pending_payment_and_reserved(
        self,
        message: Dict[str, Any],  # ProtobufDeserializer returns dict
        _key: object = None,
        _context: object = None,
    ) -> Dict:
        """Process Booking → PENDING_PAYMENT + Ticket → RESERVED (atomic operation)"""
        extract_trace_context(
            headers={
                'traceparent': message.get('traceparent', ''),
                'tracestate': message.get('tracestate', ''),
            }
        )
        booking_id = message.get('booking_id')
        reserved_seats = message.get('reserved_seats', [])

        try:
            with self.tracer.start_as_current_span(
                'consumer.process_pending_payment',
                attributes={
                    'messaging.system': 'kafka',
                    'messaging.operation': 'process',
                    'booking.id': str(booking_id) if booking_id else 'unknown',
                    'tickets.count': len(reserved_seats) if reserved_seats else 0,
                },
            ):
                Logger.base.info(
                    f'📥 [BOOKING+TICKET-{self.instance_id}] Processing: booking_id={booking_id}'
                )

                # Use portal to call async function (ensures proper async context)
                # pyrefly: ignore  # missing-attribute
                self.portal.call(self._handle_pending_payment_and_reserved_async, message)

                Logger.base.info(
                    f'✅ [BOOKING+TICKET] Completed: booking_id={booking_id}, tickets={len(reserved_seats)}'
                )
                return {'success': True}

        except Exception as e:
            Logger.base.error(f'❌ [BOOKING+TICKET] Failed: booking_id={booking_id}, error={e}')
            return {'success': False, 'error': str(e)}

    @Logger.io
    async def _handle_pending_payment_and_reserved_async(self, message: Dict[str, Any]) -> None:
        """
        Async handler for pending payment and reserved - Upsert booking with tickets

        Note: Repositories use asyncpg and manage their own connections.
        Use case directly depends on repositories, no UoW needed.
        """

        booking_id = message.get('booking_id')
        buyer_id = message.get('buyer_id')
        event_id = message.get('event_id')
        section = message.get('section')
        subsection = message.get('subsection')
        seat_selection_mode = message.get('seat_selection_mode')
        reserved_seats = message.get('reserved_seats', [])
        total_price = message.get('total_price', 0)
        subsection_stats = message.get('subsection_stats', {})
        event_stats = message.get('event_stats', {})

        # Log event-level stats for observability
        if event_stats:
            event_available = event_stats.get('available', 0)
            event_total = event_stats.get('total', 0)
            is_event_sold_out = event_available == 0

            Logger.base.info(
                f'📊 [EVENT-STATS] Event {event_id}: {event_available}/{event_total} available'
                f'{" 🎊 EVENT SOLD OUT!" if is_event_sold_out else ""}'
            )

        # Create repository (asyncpg-based, no session management needed)
        booking_command_repo = BookingCommandRepoImpl()

        # Create and execute use case (NO seat_availability_cache - uses Redis Pub/Sub now)
        use_case = UpdateBookingToPendingPaymentAndTicketToReservedUseCase(
            booking_command_repo=booking_command_repo,
            event_broadcaster=self.event_broadcaster,
        )

        # Validate and convert booking_id
        if not booking_id:
            raise ValueError('booking_id is required')

        await use_case.execute(
            booking_id=UUID(booking_id) if isinstance(booking_id, str) else booking_id,
            buyer_id=buyer_id or 0,
            event_id=event_id or 0,
            section=section or '',
            subsection=subsection or 0,
            seat_selection_mode=seat_selection_mode or 'manual',
            reserved_seats=reserved_seats,
            total_price=total_price,
            subsection_stats=subsection_stats if subsection_stats else None,
            event_stats=event_stats if event_stats else None,
        )

    @Logger.io
    def _process_failed(
        self,
        message: Dict[str, Any],  # ProtobufDeserializer returns dict
        _key: object = None,
        _context: object = None,
    ) -> Dict:
        """Process Booking → FAILED"""
        extract_trace_context(
            headers={
                'traceparent': message.get('traceparent', ''),
                'tracestate': message.get('tracestate', ''),
            }
        )
        booking_id = message.get('booking_id')

        try:
            Logger.base.info(
                f'📥 [BOOKING-FAILED-{self.instance_id}] Processing: booking_id={booking_id}'
            )

            # Use portal to call async function (ensures proper async context)
            # pyrefly: ignore  # missing-attribute
            self.portal.call(self._handle_booking_failed_async, message)

            Logger.base.info(f'✅ [BOOKING-FAILED] Completed: {booking_id}')
            return {'success': True}

        except Exception as e:
            Logger.base.error(f'❌ [BOOKING-FAILED] Failed: booking_id={booking_id}, error={e}')
            return {'success': False, 'error': str(e)}

    async def _handle_booking_failed_async(self, message: Dict[str, Any]) -> None:
        booking_id = message.get('booking_id')
        buyer_id = message.get('buyer_id')
        event_id = message.get('event_id')
        section = message.get('section')
        subsection = message.get('subsection')
        quantity = message.get('quantity')
        seat_selection_mode = message.get('seat_selection_mode')
        seat_positions = message.get('seat_positions', [])
        error_message = message.get('error_message', 'Unknown reservation error')

        # Validate required fields
        if not all([booking_id, buyer_id, event_id, section is not None, subsection is not None]):
            raise ValueError(
                f'Missing required fields in failed event: '
                f'booking_id={booking_id}, buyer_id={buyer_id}, event_id={event_id}, '
                f'section={section}, subsection={subsection}'
            )

        # Type assertions after validation
        assert booking_id is not None
        assert buyer_id is not None
        assert event_id is not None
        assert section is not None
        assert subsection is not None

        # Create repository (manages its own asyncpg connections)
        booking_command_repo = BookingCommandRepoImpl()
        use_case = UpdateBookingToFailedUseCase(
            booking_command_repo=booking_command_repo,
            event_broadcaster=self.event_broadcaster,
        )

        await use_case.execute(
            booking_id=UUID(booking_id) if isinstance(booking_id, str) else booking_id,
            buyer_id=int(buyer_id),
            event_id=int(event_id),
            section=str(section),
            subsection=int(subsection),
            quantity=int(quantity) if quantity else 0,
            seat_selection_mode=str(seat_selection_mode)
            if seat_selection_mode
            else 'best_available',
            seat_positions=seat_positions,
            error_message=error_message,
        )

    # ========== Lifecycle ==========

    def start(self) -> None:
        max_retries = 5
        retry_delay = 2  # seconds

        for attempt in range(1, max_retries + 1):
            try:
                # Setup Kafka topics
                self._setup_topics()

                Logger.base.info(
                    f'🚀 [TICKETING-{self.instance_id}] Started\n'
                    f'   📊 Event: {self.event_id}\n'
                    f'   👥 Group: {self.consumer_group_id}\n'
                    f'   🔒 Processing: {self.PROCESSING_GUARANTEE}\n'
                    f'   📦 Waiting for partition assignment...'
                )

                self.running = True
                if self.kafka_app:
                    Logger.base.info(
                        f'🎯 [TICKETING-{self.instance_id}] Running app\n'
                        f'   💡 Partition assignments will be logged when messages are processed'
                    )

                    # Run Kafka application
                    # Note: signal.signal is mocked in main.py to avoid "signal only works in main thread" error
                    Logger.base.info('🔧 [TICKETING] Starting Kafka application')
                    self.kafka_app.run()
                    break  # Success, exit retry loop

            except Exception as e:
                error_msg = str(e)

                # Check if it's a topic metadata sync issue
                if 'UNKNOWN_TOPIC_OR_PART' in error_msg and attempt < max_retries:
                    Logger.base.warning(
                        f'⚠️ [TICKETING] Attempt {attempt}/{max_retries} failed: Topic metadata not ready\n'
                        f'   🔄 Retrying in {retry_delay}s... (Kafka brokers may still be syncing)'
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff

                    # Reset kafka_app for next attempt
                    self.kafka_app = None
                    continue
                else:
                    # Fatal error or max retries reached
                    Logger.base.error(f'❌ [TICKETING] Start failed after {attempt} attempts: {e}')
                    raise

    def stop(self) -> None:
        """Stop service"""
        if not self.running:
            return

        self.running = False

        try:
            Logger.base.info('🛑 [TICKETING] Stopping consumer...')
            if self.kafka_app:
                self.kafka_app.stop()
            Logger.base.info('✅ [TICKETING] Consumer stopped')
        except Exception as e:
            Logger.base.warning(f'⚠️ [TICKETING] Stop error: {e}')


# ============================================================
# Main Entry Point
# ============================================================
# Note: Main entry point moved to start_ticketing_consumer.py
# ============================================================
