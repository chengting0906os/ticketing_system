"""
Standalone Seat Reservation Consumer Entry Point (Async)

Usage:
    PYTHONPATH=$PWD uv run python src/service/reservation/driving_adapter/start_reservation_consumer.py

Uses confluent-kafka experimental AIOConsumer for fully async message processing.
"""

import os
import signal

import anyio

from src.platform.config.di import container
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.event_publisher import close_producer
from src.platform.message_queue.kafka_topic_initializer import KafkaTopicInitializer
from src.platform.observability.tracing import TracingConfig
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.reservation.driving_adapter.reservation_mq_consumer import (
    SeatReservationConsumer,
)


async def main() -> None:
    """Main async entry point for Seat Reservation Service Consumer."""
    Logger.base.info('🚀 [Reservation Service Consumer] Starting...')

    # Setup OpenTelemetry tracing
    tracing = TracingConfig(service_name='reservation-service')
    tracing.setup()
    Logger.base.info('📊 [Reservation Service Consumer] OpenTelemetry configured')

    # Get event ID from environment
    event_id = int(os.getenv('EVENT_ID', '1'))

    # Auto-create topics before consumer starts
    topic_initializer = KafkaTopicInitializer()
    topic_initializer.ensure_topics_exist(event_id=event_id)
    Logger.base.info(f'📝 [Reservation Service Consumer] Topics ensured for EVENT_ID={event_id}')

    # Initialize Kvrocks
    try:
        await kvrocks_client.initialize()
        Logger.base.info('📡 [Reservation Service Consumer] Kvrocks initialized')
    except Exception as e:
        Logger.base.error(f'❌ [Reservation Service Consumer] Failed to initialize Kvrocks: {e}')
        raise

    consumer = SeatReservationConsumer()

    # Setup signal handlers for graceful shutdown
    shutdown_event = anyio.Event()

    def shutdown_handler(signum: int) -> None:
        Logger.base.info(f'🛑 [Reservation Service Consumer] Received signal {signum}')
        shutdown_event.set()

    try:
        # Register signal handlers and run consumer
        with anyio.open_signal_receiver(signal.SIGINT, signal.SIGTERM) as signals:

            async def signal_watcher() -> None:
                async for signum in signals:
                    shutdown_handler(signum)
                    break

            async with anyio.create_task_group() as tg:
                # Inject task group into DI container for fire-and-forget event publishing
                container.task_group.override(tg)
                Logger.base.info(
                    '🔄 [Reservation Service Consumer] Task group injected into DI container'
                )

                tg.start_soon(signal_watcher)  # type: ignore[arg-type]
                tg.start_soon(consumer.start)  # type: ignore[arg-type]

                # Wait for shutdown signal
                await shutdown_event.wait()

                # Stop consumer gracefully
                Logger.base.info(
                    '🛑 [Reservation Service Consumer] Initiating graceful shutdown...'
                )
                await consumer.stop()
                tg.cancel_scope.cancel()

    finally:
        # Close Kafka producer
        try:
            await close_producer()
            Logger.base.info('📤 [Reservation Service Consumer] Kafka producer closed')
        except Exception as e:
            Logger.base.warning(f'⚠️ [Reservation Service Consumer] Error closing producer: {e}')

        # Disconnect Kvrocks
        try:
            await kvrocks_client.disconnect()
            Logger.base.info('📡 [Reservation Service Consumer] Kvrocks disconnected')
        except Exception:
            pass

        # Shutdown tracing
        tracing.shutdown()
        Logger.base.info('📊 [Reservation Service Consumer] Tracing shutdown complete')
        Logger.base.info('👋 [Reservation Service Consumer] Shutdown complete')


if __name__ == '__main__':
    anyio.run(main)  # type: ignore[arg-type]
