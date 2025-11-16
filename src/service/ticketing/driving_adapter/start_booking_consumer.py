"""
Standalone Booking Consumer - Processes SeatsReservedEvent to create bookings

This consumer runs independently from the API service for:
- Better resource isolation
- Independent scaling
- Cleaner separation of concerns

Usage:
    PYTHONPATH=$PWD uv run python src/service/ticketing/driving_adapter/start_booking_consumer.py
"""

import os
import signal

import anyio
from anyio.from_thread import start_blocking_portal

from src.platform.config.di import container
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.kafka_topic_initializer import KafkaTopicInitializer
from src.platform.observability.tracing import TracingConfig
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.ticketing.driving_adapter.mq_consumer.booking_mq_consumer import (
    BookingMqConsumer,
)


def main() -> None:
    Logger.base.info('🚀 [Standalone Booking Consumer] Starting...')

    # Setup OpenTelemetry tracing
    tracing = TracingConfig(service_name='booking-consumer')
    tracing.setup()
    Logger.base.info('📊 [Standalone Booking Consumer] OpenTelemetry configured')

    # Get event ID from environment
    event_id = int(os.getenv('EVENT_ID', '1'))

    # Auto-create topics before consumer starts
    topic_initializer = KafkaTopicInitializer()
    topic_initializer.ensure_topics_exist(event_id=event_id)
    Logger.base.info(f'📝 [Standalone Booking Consumer] Topics ensured for EVENT_ID={event_id}')

    # Initialize consumer (NO seat_availability_cache - uses Redis Pub/Sub now)
    event_broadcaster = container.booking_event_broadcaster()
    consumer = BookingMqConsumer(
        event_broadcaster=event_broadcaster,
    )

    def run_with_portal() -> None:
        """Run consumer in thread with BlockingPortal for async-to-sync calls"""
        with start_blocking_portal() as portal:
            consumer.set_portal(portal)

            # Initialize Kvrocks for consumer event loop
            try:
                portal.call(kvrocks_client.initialize)  # type: ignore
                Logger.base.info('📡 [Standalone Booking Consumer] Kvrocks initialized')
            except Exception as e:
                Logger.base.error(
                    f'❌ [Standalone Booking Consumer] Failed to initialize Kvrocks: {e}'
                )
                raise

            # Create and inject task group for fire-and-forget event publishing
            async def run_with_task_group():
                async with anyio.create_task_group() as tg:
                    # Inject task group into DI container
                    container.task_group.override(tg)
                    Logger.base.info(
                        '🔄 [Standalone Booking Consumer] Task group injected into DI container'
                    )

                    # Keep task group alive - consumer.start() will block
                    try:
                        await anyio.sleep_forever()
                    except anyio.get_cancelled_exc_class():
                        Logger.base.info(
                            '✅ [Standalone Booking Consumer] Task group shutting down'
                        )

            # Start task group in background
            portal.start_task_soon(run_with_task_group)  # type: ignore
            Logger.base.info('🔄 [Standalone Booking Consumer] Background task group started')

            # Setup signal handlers
            def shutdown_handler(signum, frame):
                Logger.base.info(f'🛑 [Standalone Booking Consumer] Received signal {signum}')
                consumer.running = False

            signal.signal(signal.SIGINT, shutdown_handler)
            signal.signal(signal.SIGTERM, shutdown_handler)

            try:
                Logger.base.info('✅ [Standalone Booking Consumer] Starting consumer...')
                consumer.start()
            finally:
                try:
                    portal.call(kvrocks_client.disconnect)  # type: ignore
                    Logger.base.info('📡 [Standalone Booking Consumer] Kvrocks disconnected')
                except Exception:
                    pass

                # Shutdown tracing
                tracing.shutdown()
                Logger.base.info('📊 [Standalone Booking Consumer] Tracing shutdown complete')

    run_with_portal()


if __name__ == '__main__':
    main()
