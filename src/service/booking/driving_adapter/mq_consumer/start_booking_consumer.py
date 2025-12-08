"""
Standalone Booking Service Consumer Entry Point (Async)

Usage:
    PYTHONPATH=$PWD uv run python src/service/booking/driving_adapter/mq_consumer/start_booking_consumer.py

Uses confluent-kafka experimental AIOConsumer for fully async message processing.
"""

import os
import signal

import anyio

from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.event_publisher import close_producer
from src.platform.message_queue.kafka_topic_initializer import KafkaTopicInitializer
from src.platform.observability.tracing import TracingConfig
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.booking.driving_adapter.mq_consumer.booking_mq_consumer import (
    BookingConsumer,
)


async def main() -> None:
    """Main async entry point for Booking Service Consumer."""
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

    # Initialize Kvrocks
    try:
        await kvrocks_client.initialize()
        Logger.base.info('📡 [Booking Service Consumer] Kvrocks initialized')
    except Exception as e:
        Logger.base.error(f'❌ [Booking Service Consumer] Failed to initialize Kvrocks: {e}')
        raise

    consumer = BookingConsumer()

    # Setup signal handlers for graceful shutdown
    shutdown_event = anyio.Event()

    def shutdown_handler(signum: int) -> None:
        Logger.base.info(f'🛑 [Booking Service Consumer] Received signal {signum}')
        shutdown_event.set()

    try:
        # Register signal handlers
        with anyio.open_signal_receiver(signal.SIGINT, signal.SIGTERM) as signals:

            async def signal_watcher() -> None:
                async for signum in signals:
                    shutdown_handler(signum)
                    break

            async with anyio.create_task_group() as tg:
                tg.start_soon(signal_watcher)  # type: ignore[arg-type]
                tg.start_soon(consumer.start)  # type: ignore[arg-type]

                # Wait for shutdown signal
                await shutdown_event.wait()

                # Stop consumer gracefully
                Logger.base.info('🛑 [Booking Service Consumer] Initiating graceful shutdown...')
                await consumer.stop()
                tg.cancel_scope.cancel()

    finally:
        # Close Kafka producer
        try:
            await close_producer()
            Logger.base.info('📤 [Booking Service Consumer] Kafka producer closed')
        except Exception as e:
            Logger.base.warning(f'⚠️ [Booking Service Consumer] Error closing producer: {e}')

        # Disconnect Kvrocks
        try:
            await kvrocks_client.disconnect()
            Logger.base.info('📡 [Booking Service Consumer] Kvrocks disconnected')
        except Exception:
            pass

        # Shutdown tracing
        tracing.shutdown()
        Logger.base.info('📊 [Booking Service Consumer] Tracing shutdown complete')
        Logger.base.info('👋 [Booking Service Consumer] Shutdown complete')


if __name__ == '__main__':
    anyio.run(main)  # type: ignore[arg-type]
