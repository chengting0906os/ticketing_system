"""
Ticketing MQ Consumer - Unified PostgreSQL State Manager

Integrated Responsibilities (2 topics):
1. Booking + Ticket State Sync (Atomic Operation):
   - pending_payment_and_reserved: After successful seat reservation, simultaneously update Booking to PENDING_PAYMENT and Ticket to RESERVED

2. Booking Failure Handling:
   - failed: Update order status after seat reservation failure

Important:
- This consumer **only operates on PostgreSQL**, doesn't touch Kvrocks!
- Kvrocks state management is the responsibility of seat_reservation_consumer
- Merged topics ensure atomicity of Booking and Ticket state updates

Features:
- Error Handling: Use Quix Streams callback to handle errors
- Dead Letter Queue: Failed messages sent to DLQ
"""

import os
import time
from typing import TYPE_CHECKING, Any, Dict, Optional

import orjson
from anyio.from_thread import BlockingPortal, start_blocking_portal
from opentelemetry import trace
from uuid_utils import UUID
from quixstreams import Application


if TYPE_CHECKING:
    from anyio.from_thread import BlockingPortal

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.kafka_constant_builder import (
    KafkaConsumerGroupBuilder,
    KafkaTopicBuilder,
)
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
from src.service.ticketing.driven_adapter.repo.booking_query_repo_impl import (
    BookingQueryRepoImpl,
)
from src.platform.event.i_in_memory_broadcaster import IInMemoryEventBroadcaster


class KafkaConfig:
    """Kafka configuration - Supports Exactly-Once semantics"""

    def __init__(self, *, event_id: int, instance_id: str, retries: int = 3):
        """
        Args:
            event_id: Event ID
            instance_id: Consumer instance ID (used to generate unique transactional.id)
            retries: Producer retry count
        """
        from src.platform.message_queue.kafka_constant_builder import (
            KafkaProducerTransactionalIdBuilder,
        )

        self.event_id = event_id
        self.instance_id = instance_id
        self.retries = retries
        self.transactional_id = KafkaProducerTransactionalIdBuilder.ticketing_service(
            event_id=event_id, instance_id=instance_id
        )

    @property
    def producer_config(self) -> Dict:
        """
        Producer configuration - Enable transaction support

        Note: Quix Streams with processing_guarantee='exactly-once' requires:
        - transactional.id: Uniquely identifies this producer, enabling exactly-once
        - enable.idempotence = True (set automatically)
        - acks = 'all' (set automatically)
        """
        return {
            'transactional.id': self.transactional_id,  # 🔑 Key for Exactly-Once
            'retries': self.retries,
        }

    @property
    def consumer_config(self) -> Dict:
        """
        Consumer configuration

        Note: Quix Streams with processing_guarantee='exactly-once' already sets:
        - enable.auto.commit = False (manual commit via transactions)
        - isolation.level = 'read_committed' (only read committed messages)

        We only set auto.offset.reset for first-time startup behavior:
        - 'latest': Skip old messages, start from newest (recommended for production)
        - 'earliest': Process all messages from beginning (use for testing/recovery)
        """
        return {
            'auto.offset.reset': 'latest',
        }


class TicketingMqConsumer:
    """
    Integrated Ticketing MQ Consumer (PostgreSQL State Management)

    Handles 2 topics:
    - Booking + Ticket atomic update (pending_payment + reserved)
    - Booking failure handling (failed)

    All PostgreSQL operations, stateless processing
    """

    def __init__(
        self,
        *,
        event_broadcaster: IInMemoryEventBroadcaster,
        seat_availability_cache: Any = None,
    ):
        self.event_id = int(os.getenv('EVENT_ID', '1'))
        # Generate unique instance_id per worker process using PID to avoid transactional.id conflicts
        base_instance_id = settings.KAFKA_CONSUMER_INSTANCE_ID
        self.instance_id = f'{base_instance_id}-pid-{os.getpid()}'
        self.consumer_group_id = os.getenv(
            'CONSUMER_GROUP_ID',
            KafkaConsumerGroupBuilder.ticketing_service(event_id=self.event_id),
        )

        self.kafka_config = KafkaConfig(event_id=self.event_id, instance_id=self.instance_id)
        self.kafka_app: Optional[Application] = None
        self.running = False
        self.portal: Optional['BlockingPortal'] = None
        self.event_broadcaster = event_broadcaster
        self.seat_availability_cache = seat_availability_cache
        self.tracer = trace.get_tracer(__name__)

        # DLQ configuration
        self.dlq_topic = KafkaTopicBuilder.ticketing_dlq(event_id=self.event_id)

        # Use cases (lazy initialization)
        self.update_booking_to_pending_payment_use_case: Any = None
        self.update_booking_to_failed_use_case: Any = None

    def set_portal(self, portal: 'BlockingPortal') -> None:
        """Set BlockingPortal for calling async functions from sync code"""
        self.portal = portal

    def _on_processing_error(self, exc: Exception, row: Any, _logger: Any) -> bool:
        """
        Quix Streams error handling callback

        This callback is called when message processing fails.
        Error messages are sent directly to DLQ, no retry at this layer.

        Returns:
            True: Ignore error and commit offset (message sent to DLQ)
            False: Propagate error and don't commit offset (stop consumer)
        """
        error_msg = str(exc)

        Logger.base.error(f'❌ [TICKETING-ERROR-CALLBACK] Processing error, sending to DLQ: {exc}')

        # Send to DLQ
        if row and hasattr(row, 'value'):
            message = row.value
            self._send_to_dlq(
                message=message,
                original_topic='unknown',  # Quix doesn't provide topic in callback
                error=error_msg,
                retry_count=0,
            )

        # Return True: Commit offset, message sent to DLQ
        return True

    @Logger.io
    def _create_kafka_app(self) -> Application:
        """Create Kafka application with Exactly-Once support and error handling configuration"""
        app = Application(
            broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=self.consumer_group_id,
            processing_guarantee='exactly-once',  # 🆕 Enable exactly-once processing
            commit_interval=0,  # 🆕 Disable auto-commit interval, let transactions manage
            producer_extra_config=self.kafka_config.producer_config,
            consumer_extra_config=self.kafka_config.consumer_config,
            on_processing_error=self._on_processing_error,  # 🆕 Error handling callback
        )

        Logger.base.info(
            f'🎫 [TICKETING] Created exactly-once Kafka app\n'
            f'   👥 Group: {self.consumer_group_id}\n'
            f'   🎫 Event: {self.event_id}\n'
            f'   🔒 Processing: exactly-once\n'
            f'   🔑 Transactional ID: {self.kafka_config.transactional_id}\n'
            f'   ⚠️ Error handling: enabled'
        )
        return app

    @Logger.io
    def _setup_topics(self):
        """Setup processing logic for 2 topics - Use Kafka transactions for Exactly Once"""
        if not self.kafka_app:
            self.kafka_app = self._create_kafka_app()

        # Define topic configuration
        topics = {
            'pending_payment_and_reserved': (
                KafkaTopicBuilder.update_booking_status_to_pending_payment_and_ticket_status_to_reserved_in_postgresql(
                    event_id=self.event_id
                ),
                self._process_pending_payment_and_reserved,
            ),
            'failed': (
                KafkaTopicBuilder.update_booking_status_to_failed(event_id=self.event_id),
                self._process_failed,
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

    # ========== DLQ Helper ==========

    @Logger.io
    def _send_to_dlq(self, *, message: Dict, original_topic: str, error: str, retry_count: int):
        """Send failed message to DLQ"""
        if not self.kafka_app:
            Logger.base.error('❌ [TICKETING-DLQ] Kafka app not initialized')
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
        self, message: Dict, key: Any = None, context: Any = None
    ) -> Dict:
        """Process Booking → PENDING_PAYMENT + Ticket → RESERVED (atomic operation)"""
        # Extract trace context from message for distributed tracing
        trace_headers = message.get('_trace_headers', {})
        if trace_headers:
            extract_trace_context(headers=trace_headers)

        booking_id = message.get('booking_id')
        reserved_seats = message.get('reserved_seats', [])

        # Extract partition info from Quix Streams context
        partition_info = ''
        if hasattr(context, 'partition'):
            partition_info = f' | partition={context.partition}'

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
                    f'📥 [BOOKING+TICKET-{self.instance_id}] Processing: booking_id={booking_id}{partition_info}'
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

    async def _handle_pending_payment_and_reserved_async(self, message: Dict[str, Any]):
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
        seat_prices = message.get('seat_prices', {})
        total_price = message.get('total_price', 0)
        subsection_stats = message.get('subsection_stats', {})
        event_stats = message.get('event_stats', {})

        # Update cache with stats from Kvrocks (event-driven cache update)
        if self.seat_availability_cache and subsection_stats:
            section_id = f'{section}-{subsection}'
            self.seat_availability_cache.update_cache(
                event_id=event_id,
                section_id=section_id,
                stats=subsection_stats,
            )
            Logger.base.debug(
                f'📊 [CACHE-UPDATE] Updated cache for {section_id}: '
                f'available={subsection_stats.get("available")}'
            )

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

        # Create and execute use case with direct repository injection + broadcaster
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
            seat_prices=seat_prices,
            total_price=total_price,
            subsection_stats=subsection_stats if subsection_stats else None,
            event_stats=event_stats if event_stats else None,
        )

    @Logger.io
    def _process_failed(self, message: Dict, key: Any = None, context: Any = None) -> Dict:
        """Process Booking → FAILED"""
        booking_id = message.get('booking_id')

        # Extract partition info from Quix Streams context
        partition_info = ''
        if hasattr(context, 'partition'):
            partition_info = f' | partition={context.partition}'

        try:
            Logger.base.info(
                f'📥 [BOOKING-FAILED-{self.instance_id}] Processing: booking_id={booking_id}{partition_info}'
            )

            # Use portal to call async function (ensures proper async context)
            # pyrefly: ignore  # missing-attribute
            self.portal.call(self._handle_failed_async, message)

            Logger.base.info(f'✅ [BOOKING-FAILED] Completed: {booking_id}')
            return {'success': True}

        except Exception as e:
            Logger.base.error(f'❌ [BOOKING-FAILED] Failed: booking_id={booking_id}, error={e}')
            return {'success': False, 'error': str(e)}

    async def _handle_failed_async(self, message: Dict[str, Any]):
        """
        Async handler for failed booking

        Note: Repositories use asyncpg and manage their own connections.
        Use case directly depends on repositories, no UoW needed.
        """
        booking_id = message.get('booking_id')
        buyer_id = message.get('buyer_id')
        reason = message.get('error_message', 'Unknown')

        # Create repositories (they manage their own asyncpg connections)
        booking_command_repo = BookingCommandRepoImpl()
        booking_query_repo = BookingQueryRepoImpl()

        # Create and execute use case with direct repository injection + broadcaster
        use_case = UpdateBookingToFailedUseCase(
            booking_query_repo=booking_query_repo,
            booking_command_repo=booking_command_repo,
            event_broadcaster=self.event_broadcaster,
        )

        # Validate and convert booking_id
        if not booking_id:
            raise ValueError('booking_id is required')

        await use_case.execute(
            booking_id=UUID(booking_id) if isinstance(booking_id, str) else booking_id,
            buyer_id=buyer_id or 0,
            error_message=reason,
        )

    # ========== Lifecycle ==========

    def start(self):
        """Start service - Support topic metadata sync retry"""
        import time

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
                    f'   🔒 Processing: exactly-once\n'
                    f'   📦 Waiting for partition assignment...'
                )

                self.running = True
                if self.kafka_app:
                    Logger.base.info(
                        f'🎯 [TICKETING-{self.instance_id}] Running app\n'
                        f'   💡 Partition assignments will be logged when messages are processed'
                    )
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

    def stop(self):
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


def main():
    """Main program entry point"""
    # Initialize broadcaster (shared instance for SSE)
    from src.platform.event.in_memory_broadcaster import InMemoryEventBroadcasterImpl
    from src.service.ticketing.driven_adapter.state.seat_availability_query_handler_impl import (
        SeatAvailabilityQueryHandlerImpl,
    )

    broadcaster = InMemoryEventBroadcasterImpl()
    seat_cache = SeatAvailabilityQueryHandlerImpl()
    consumer = TicketingMqConsumer(
        event_broadcaster=broadcaster, seat_availability_cache=seat_cache
    )

    try:
        # Start BlockingPortal and create shared event loop
        with start_blocking_portal() as portal:
            consumer.set_portal(portal)
            consumer.start()

    except KeyboardInterrupt:
        Logger.base.info('⚠️ [TICKETING] Received interrupt signal')
        try:
            consumer.stop()
        except Exception:
            pass
    except Exception as e:
        Logger.base.error(f'💥 [TICKETING] Consumer error: {e}')
        try:
            consumer.stop()
        except:
            pass
    finally:
        Logger.base.info('🧹 Cleaning up resources...')


if __name__ == '__main__':
    main()
