"""
Standalone Booking Service Consumer Entry Point

Usage:
    PYTHONPATH=$PWD uv run python src/service/booking/driving_adapter/mq_consumer/start_booking_consumer.py
"""

import os
import signal
import types

from anyio.from_thread import start_blocking_portal

from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.kafka_topic_initializer import KafkaTopicInitializer
from src.platform.observability.tracing import TracingConfig
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.booking.driving_adapter.mq_consumer.booking_mq_consumer import (
    BookingConsumer,
)


def main() -> None:
    Logger.base.info('🚀 [Booking Service Consumer] Starting...')

    # Setup OpenTelemetry tracing
    tracing = TracingConfig(service_name='booking-service')
    tracing.setup()
    Logger.base.info('📊 [Booking Service Consumer] OpenTelemetry configured')

    # Get event ID from environment
    event_id = int(os.getenv('EVENT_ID', '1'))

    # Auto-create topics before consumer starts
    topic_initializer = KafkaTopicInitializer()
    topic_initializer.ensure_topics_exist(event_id=event_id)
    Logger.base.info(f'📝 [Booking Service Consumer] Topics ensured for EVENT_ID={event_id}')

    consumer = BookingConsumer()

    def run_with_portal() -> None:
        """Run consumer in thread with BlockingPortal for async-to-sync calls"""
        with start_blocking_portal() as portal:
            consumer.set_portal(portal)

            # Initialize Kvrocks for consumer event loop
            try:
                portal.call(kvrocks_client.initialize)  # type: ignore
                Logger.base.info('📡 [Booking Service Consumer] Kvrocks initialized')
            except Exception as e:
                Logger.base.error(
                    f'❌ [Booking Service Consumer] Failed to initialize Kvrocks: {e}'
                )
                raise

            # Setup signal handlers
            def shutdown_handler(signum: int, frame: types.FrameType | None) -> None:
                Logger.base.info(f'🛑 [Booking Service Consumer] Received signal {signum}')
                consumer.running = False

            signal.signal(signal.SIGINT, shutdown_handler)
            signal.signal(signal.SIGTERM, shutdown_handler)

            try:
                Logger.base.info('✅ [Booking Service Consumer] Starting consumer...')
                consumer.start()
            finally:
                try:
                    portal.call(kvrocks_client.disconnect)  # type: ignore
                    Logger.base.info('📡 [Booking Service Consumer] Kvrocks disconnected')
                except Exception:
                    pass

                tracing.shutdown()
                Logger.base.info('📊 [Booking Service Consumer] Tracing shutdown complete')

    run_with_portal()


if __name__ == '__main__':
    main()
