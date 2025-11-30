"""
Seat Reservation Consumer - Seat Selection Router
Responsibility: Manage Kvrocks seat state and handle reservation requests

Features:
- Retry mechanism: Exponential backoff
- Dead Letter Queue: Failed messages sent to DLQ
"""

import os
import time
from typing import TYPE_CHECKING, Any, Dict, Literal, Optional

from anyio.from_thread import BlockingPortal
from opentelemetry import trace
import orjson
from quixstreams import Application


if TYPE_CHECKING:
    from anyio.from_thread import BlockingPortal

from src.platform.config.core_setting import KafkaConfig, settings
from src.platform.config.di import container
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.kafka_constant_builder import (
    KafkaConsumerGroupBuilder,
    KafkaTopicBuilder,
)
from src.platform.observability.tracing import extract_trace_context
from src.service.seat_reservation.app.dto import (
    FinalizeSeatPaymentRequest,
    ReservationRequest,
)
from src.service.shared_kernel.app.dto import ReleaseSeatsBatchRequest
from src.service.shared_kernel.domain.value_object import SubsectionConfig


class SeatReservationConsumer:
    """
    Seat Reservation Consumer - Stateless Router

    Listens to 3 Topics:
    1. ticket_reserving_request_to_reserved_in_kvrocks - Reservation requests
    2. release_ticket_status_to_available_in_kvrocks - Release seats
    3. finalize_ticket_status_to_paid_in_kvrocks - Finalize payment
    """

    PROCESSING_GUARANTEE: Literal['at-least-once', 'exactly-once'] = 'at-least-once'

    def __init__(self):
        self.event_id = int(os.getenv('EVENT_ID', '1'))
        # Use consumer instance_id for consumer group identification
        self.consumer_instance_id = settings.KAFKA_CONSUMER_INSTANCE_ID
        # Alias for backward compatibility
        self.instance_id = self.consumer_instance_id
        self.consumer_group_id = os.getenv(
            'CONSUMER_GROUP_ID',
            KafkaConsumerGroupBuilder.seat_reservation_service(event_id=self.event_id),
        )

        # KafkaConfig now gets producer instance_id from settings directly (lazy evaluation)
        self.kafka_config = KafkaConfig(event_id=self.event_id, service='seat_reservation')
        self.kafka_app: Optional[Application] = None
        self.running = False
        self.portal: Optional['BlockingPortal'] = None
        self.tracer = trace.get_tracer(__name__)

        # DLQ configuration
        self.dlq_topic = KafkaTopicBuilder.seat_reservation_dlq(event_id=self.event_id)

        # Use cases (lazy initialization)
        self.reserve_seats_use_case: Any = None
        self.release_seat_use_case: Any = None
        self.finalize_seat_payment_use_case: Any = None

    def set_portal(self, portal: 'BlockingPortal') -> None:
        """Set BlockingPortal for calling async functions from sync code"""
        self.portal = portal

    def _on_processing_error(self, exc: Exception, row: Any, _logger: Any) -> bool:
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
            f'🪑 [SEAT-RESERVATION] Created Kafka app\n'
            f'   👥 Group: {self.consumer_group_id}\n'
            f'   🎫 Event: {self.event_id}\n'
            f'   🔒 Processing: {self.PROCESSING_GUARANTEE}\n'
            f'   ⚠️ Error handling: enabled'
        )
        return app

    @Logger.io
    def _setup_topics(self):
        if not self.kafka_app:
            self.kafka_app = self._create_kafka_app()

        # Define topic configuration
        topics = {
            'reservation': (
                KafkaTopicBuilder.ticket_reserving_request_to_reserved_in_kvrocks(
                    event_id=self.event_id
                ),
                self._process_reservation_request,
            ),
            'release': (
                KafkaTopicBuilder.release_ticket_status_to_available_in_kvrocks(
                    event_id=self.event_id
                ),
                self._process_release_seat,
            ),
            'finalize': (
                KafkaTopicBuilder.finalize_ticket_status_to_paid_in_kvrocks(event_id=self.event_id),
                self._process_finalize_payment,
            ),
        }

        # Register all topics - Use stateless mode, rely on Kafka transactions
        for name, (topic_name, handler) in topics.items():
            topic = self.kafka_app.topic(
                name=topic_name,
                key_serializer='str',
                value_serializer='json',
            )

            # Use stateless processing, rely on Kafka transactions for exactly once guarantee
            self.kafka_app.dataframe(topic=topic).apply(handler, stateful=False)
            Logger.base.info(f'   ✓ {name.capitalize()} topic configured (stateless + transaction)')

        Logger.base.info('✅ All topics configured (exactly once via Kafka transactions)')

    # ========== Retry and DLQ Helpers ==========

    @Logger.io
    def _send_to_dlq(self, *, message: Dict, original_topic: str, error: str, retry_count: int):
        if not self.kafka_app:
            Logger.base.error('❌ [DLQ] Kafka app not initialized')
            return

        try:
            # Build DLQ message (includes original message and error info)
            dlq_message = {
                'original_message': message,
                'original_topic': original_topic,
                'error': error,
                'retry_count': retry_count,
                'timestamp': time.time(),
                'instance_id': self.instance_id,
            }

            # Send to DLQ (use aggregate_id as key to maintain order)
            # Serialize message to JSON
            serialized_message = orjson.dumps(dlq_message)

            with self.kafka_app.get_producer() as producer:
                producer.produce(
                    topic=self.dlq_topic,
                    key=str(message.get('aggregate_id', 'unknown')),
                    value=serialized_message,
                )

            Logger.base.warning(
                f'📮 [DLQ] Sent to DLQ: {message.get("aggregate_id")} '
                f'after {retry_count} retries, error: {error}'
            )

        except Exception as e:
            Logger.base.error(f'❌ [DLQ] Failed to send to DLQ: {e}')

    # ========== Message Handlers ==========

    def _process_reservation_request(
        self, message: Dict, key: Any = None, context: Any = None
    ) -> Dict:
        """
        Process reservation request - Simplified version, errors handled by on_processing_error callback

        Note: No application-layer retry, let Quix Streams error callback handle errors
        This way the consumer won't be blocked
        """
        # Extract trace context from message for distributed tracing
        trace_headers = message.get('_trace_headers', {})
        if trace_headers:
            extract_trace_context(headers=trace_headers)

        event_id = message.get('event_id', self.event_id)

        # Extract partition info from Quix Streams context
        partition_info = ''
        if hasattr(context, 'topic') and hasattr(context, 'partition'):
            partition_info = f' | partition={context.partition}, offset={context.offset}'

        booking_id = message.get('booking_id', 'unknown')

        with self.tracer.start_as_current_span(
            'consumer.process_reservation',
            attributes={
                'messaging.system': 'kafka',
                'messaging.operation': 'process',
                'booking.id': booking_id,
                'event.id': event_id,
            },
        ):
            Logger.base.info(
                f'\033[94m🎫 [RESERVATION-{self.instance_id}] Processing: booking_id={booking_id}{partition_info}\033[0m'
            )

            # Execute reservation logic (exceptions will be caught by on_processing_error)
            # pyrefly: ignore  # missing-attribute
            result = self.portal.call(self._handle_reservation_async, message)

            return {'success': True, 'result': result}

    @Logger.io
    def _process_release_seat(self, message: Dict, key: Any = None, context: Any = None) -> Dict:
        """Process seat release - Support DLQ (release operations usually don't need retry)"""
        # Extract trace context from message for distributed tracing
        trace_headers = message.get('_trace_headers', {})
        if trace_headers:
            extract_trace_context(headers=trace_headers)

        # Extract partition info
        partition_info = ''
        if hasattr(context, 'partition'):
            partition_info = f' | partition={context.partition}'

        # Handle both old format (seat_id) and new format (seat_positions)
        seat_id = message.get('seat_id')
        seat_positions = message.get('seat_positions', [])

        if seat_id:
            # Legacy single seat release
            seat_positions = [seat_id]
        elif not seat_positions:
            error_msg = 'Missing seat_id or seat_positions'
            self._send_to_dlq(
                message=message,
                original_topic='release_ticket_status_to_available_in_kvrocks',
                error=error_msg,
                retry_count=0,
            )
            return {'success': False, 'error': error_msg, 'sent_to_dlq': True}

        booking_id = message.get('booking_id', 'unknown')
        event_id = message.get('event_id', self.event_id)

        with self.tracer.start_as_current_span(
            'consumer.process_release',
            attributes={
                'messaging.system': 'kafka',
                'messaging.operation': 'process',
                'booking.id': booking_id,
            },
        ):
            try:
                # PERFORMANCE OPTIMIZATION: Release all seats in a SINGLE batch call
                # instead of N sequential calls to reduce portal overhead
                Logger.base.info(
                    f'🔓 [RELEASE-{self.instance_id}] Releasing {len(seat_positions)} seats in batch{partition_info}'
                )

                batch_request = ReleaseSeatsBatchRequest(seat_ids=seat_positions, event_id=event_id)
                # pyrefly: ignore  # missing-attribute
                result = self.portal.call(self.release_seat_use_case.execute_batch, batch_request)

                # Log results

                return {
                    'success': True,
                    'released_seats': result.successful_seats,
                    'failed_seats': result.failed_seats,
                    'total_released': result.total_released,
                }

            except Exception as e:
                Logger.base.error(f'❌ [RELEASE] {e}')
                # Send to DLQ
                self._send_to_dlq(
                    message=message,
                    original_topic='release_ticket_status_to_available_in_kvrocks',
                    error=str(e),
                    retry_count=0,
                )
                return {'success': False, 'error': str(e), 'sent_to_dlq': True}

    @Logger.io
    def _process_finalize_payment(
        self, message: Dict, key: Any = None, context: Any = None
    ) -> Dict:
        """Process payment finalization - Support DLQ (payment finalization operations usually don't need retry)"""
        # Extract partition info
        partition_info = ''
        if hasattr(context, 'partition'):
            partition_info = f' | partition={context.partition}'

        seat_id = message.get('seat_id')
        if not seat_id:
            error_msg = 'Missing seat_id'
            self._send_to_dlq(
                message=message,
                original_topic='finalize_ticket_status_to_paid_in_kvrocks',
                error=error_msg,
                retry_count=0,
            )
            return {'success': False, 'error': error_msg, 'sent_to_dlq': True}

        try:
            request = FinalizeSeatPaymentRequest(
                seat_id=seat_id,
                event_id=self.event_id,
            )

            # pyrefly: ignore  # missing-attribute
            result = self.portal.call(self.finalize_seat_payment_use_case.execute, request)

            if result.success:
                Logger.base.info(f'💰 [FINALIZE-{self.instance_id}] {seat_id}{partition_info}')
                return {'success': True, 'seat_id': seat_id}

            # Use case execution failed, send to DLQ
            self._send_to_dlq(
                message=message,
                original_topic='finalize_ticket_status_to_paid_in_kvrocks',
                error=result.error_message or 'Unknown error',
                retry_count=0,
            )
            return {'success': False, 'error': result.error_message, 'sent_to_dlq': True}

        except Exception as e:
            Logger.base.error(f'❌ [FINALIZE] {e}')
            # Send to DLQ
            self._send_to_dlq(
                message=message,
                original_topic='finalize_ticket_status_to_paid_in_kvrocks',
                error=str(e),
                retry_count=0,
            )
            return {'success': False, 'error': str(e), 'sent_to_dlq': True}

    # ========== Reservation Logic ==========

    async def _handle_reservation_async(self, event_data: Any) -> bool:
        """
        Process seat reservation event - Only responsible for routing to use case

        Note: Don't catch exceptions, let them propagate to upper-level retry logic
        """
        parsed = self._parse_event_data(event_data)
        if not parsed:
            error_msg = 'Failed to parse event data'
            Logger.base.error(f'❌ [RESERVATION] {error_msg}')
            raise ValueError(error_msg)

        command = self._create_reservation_command(parsed)
        Logger.base.info(f'🎯 [RESERVATION] booking_id={command["booking_id"]}')

        await self._execute_reservation(command)
        return True

    def _parse_event_data(self, event_data: Any) -> Optional[Dict]:
        """Parse event data"""
        try:
            if isinstance(event_data, dict):
                return event_data
            if isinstance(event_data, str):
                return orjson.loads(event_data)
            if hasattr(event_data, '__dict__'):
                return dict(vars(event_data))

            Logger.base.error(f'❌ Unknown event data type: {type(event_data)}')
            return None

        except Exception as e:
            Logger.base.error(f'❌ Parse failed: {e}')
            return None

    def _create_reservation_command(self, event_data: Dict) -> Dict:
        """Create reservation command

        Note: publish_domain_event spreads event fields with **event.__dict__
        and removes 'aggregate_id' to avoid duplication. All fields including
        booking_id, buyer_id, event_id are at top level.
        """
        booking_id = event_data.get('booking_id')
        buyer_id = event_data.get('buyer_id')
        event_id = event_data.get('event_id')

        if not all([booking_id, buyer_id, event_id]):
            raise ValueError('Missing required fields in event data')

        # Extract config from upstream (required - fail fast if missing)
        config = event_data['config']

        return {
            'booking_id': booking_id,
            'buyer_id': buyer_id,
            'event_id': event_id,
            'section': event_data['section'],
            'subsection': event_data['subsection'],
            'quantity': event_data['quantity'],
            'seat_selection_mode': event_data['seat_selection_mode'],
            'seat_positions': event_data.get('seat_positions', []),
            # Config from upstream (avoids redundant Kvrocks lookups in Lua scripts)
            'rows': config['rows'],
            'cols': config['cols'],
            'price': config['price'],
        }

    async def _execute_reservation(self, command: Dict) -> bool:
        """Execute seat reservation - Only responsible for calling use case"""
        try:
            # Build config from upstream (required - fail fast if missing)
            config = SubsectionConfig(
                rows=command['rows'],
                cols=command['cols'],
                price=command['price'],
            )

            request = ReservationRequest(
                booking_id=command['booking_id'],
                buyer_id=command['buyer_id'],
                event_id=command['event_id'],
                selection_mode=command['seat_selection_mode'],
                quantity=command['quantity'],
                seat_positions=command['seat_positions'],
                section_filter=command['section'],
                subsection_filter=command['subsection'],
                config=config,
            )

            # Call use case (use case is responsible for sending success/failure events)
            await self.reserve_seats_use_case.reserve_seats(request)
            return True

        except Exception as e:
            Logger.base.error(f'❌ [EXECUTE] Exception: {e}')
            return False

    # ========== Lifecycle ==========

    def start(self):
        """Start service - Support topic metadata sync retry"""
        max_retries = 5
        retry_delay = 2  # seconds

        for attempt in range(1, max_retries + 1):
            try:
                # Initialize use cases
                self.reserve_seats_use_case = container.reserve_seats_use_case()
                self.release_seat_use_case = container.release_seat_use_case()
                self.finalize_seat_payment_use_case = container.finalize_seat_payment_use_case()

                # Setup Kafka
                self._setup_topics()

                Logger.base.info(
                    f'🚀 [SEAT-RESERVATION-{self.instance_id}] Started\n'
                    f'   📊 Event: {self.event_id}\n'
                    f'   👥 Group: {self.consumer_group_id}\n'
                    f'   🔒 Processing: {self.PROCESSING_GUARANTEE}\n'
                    f'   📦 Waiting for partition assignment...'
                )

                self.running = True
                if self.kafka_app:
                    Logger.base.info(
                        f'🎯 [SEAT-RESERVATION-{self.instance_id}] Running app\n'
                        f'   💡 Partition assignments will be logged when messages are processed'
                    )
                    self.kafka_app.run()
                    break  # Success, exit retry loop

            except Exception as e:
                error_msg = str(e)

                # Check if it's a topic metadata sync issue
                if 'UNKNOWN_TOPIC_OR_PART' in error_msg and attempt < max_retries:
                    Logger.base.warning(
                        f'⚠️ [SEAT-RESERVATION] Attempt {attempt}/{max_retries} failed: Topic metadata not ready\n'
                        f'   🔄 Retrying in {retry_delay}s... (Kafka brokers may still be syncing)'
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff

                    # Reset kafka_app for next attempt
                    self.kafka_app = None
                    continue
                else:
                    # Fatal error or max retries reached
                    Logger.base.error(
                        f'❌ [SEAT-RESERVATION] Start failed after {attempt} attempts: {e}'
                    )
                    raise

    def stop(self):
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

        Logger.base.info('🛑 Consumer stopped')


# ============================================================
# Note: Main entry point moved to start_seat_reservation_consumer.py
# ============================================================
