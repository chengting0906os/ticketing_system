"""
Standalone Booking Service Entry Point

Usage:
    PYTHONPATH=$PWD uv run python src/service/ticketing/driving_adapter/mq_consumer/start_booking_consumer.py
"""

import os
import signal

import anyio
from anyio.from_thread import start_blocking_portal

from src.platform.config.di import container
from src.platform.database.asyncpg_setting import get_asyncpg_pool, warmup_asyncpg_pool
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.kafka_topic_initializer import KafkaTopicInitializer
from src.platform.observability.tracing import TracingConfig
from src.platform.state.kvrocks_client import kvrocks_client
from src.platform.state.lua_script_executor import lua_script_executor
from src.service.ticketing.driving_adapter.mq_consumer.booking_mq_consumer import (
    BookingMqConsumer,
)


def main() -> None:
    """Start Booking Service with BlockingPortal"""
    Logger.base.info('🚀 [Booking Service] Starting...')

    # Setup OpenTelemetry tracing
    tracing = TracingConfig(service_name='booking-service')
    tracing.setup()
    Logger.base.info('📊 [Booking Service] OpenTelemetry configured')

    # Get event ID from environment
    event_id = int(os.getenv('EVENT_ID', '1'))

    # Auto-create topics before consumer starts
    topic_initializer = KafkaTopicInitializer()
    topic_initializer.ensure_topics_exist(event_id=event_id)
    Logger.base.info(f'📝 [Booking Service] Topics ensured for EVENT_ID={event_id}')

    # Get dependencies from DI container
    event_broadcaster = container.booking_event_broadcaster()
    seat_availability_cache = container.seat_availability_query_handler()
    consumer = BookingMqConsumer(
        event_broadcaster=event_broadcaster,
        seat_availability_cache=seat_availability_cache,
    )

    def run_with_portal() -> None:
        with start_blocking_portal() as portal:
            consumer.set_portal(portal)

            # Initialize Kvrocks for consumer event loop
            try:
                client = portal.call(kvrocks_client.initialize)  # type: ignore
                Logger.base.info('📡 [Booking Service] Kvrocks initialized')

                # Initialize Lua scripts
                portal.call(lambda: lua_script_executor.initialize(client=client))  # type: ignore
                Logger.base.info('🔥 [Booking Service] Lua scripts loaded')
            except Exception as e:
                Logger.base.error(f'❌ [Booking Service] Failed to initialize Kvrocks/Lua: {e}')
                raise

            # Initialize asyncpg pool for consumer event loop
            try:
                portal.call(get_asyncpg_pool)  # type: ignore[arg-type]
                Logger.base.info('🏊 [Booking Service] Asyncpg pool initialized')
                portal.call(warmup_asyncpg_pool)  # type: ignore[arg-type]
                Logger.base.info('🔥 [Booking Service] Asyncpg pool warmed up')
            except Exception as e:
                Logger.base.error(f'❌ [Booking Service] Failed to initialize asyncpg: {e}')
                raise

            # Create and inject task group for fire-and-forget event publishing
            # We need to keep the task group alive during consumer execution
            async def run_with_task_group():
                async with anyio.create_task_group() as tg:
                    # Inject task group into DI container
                    container.task_group.override(tg)
                    Logger.base.info('🔄 [Booking Service] Task group injected into DI container')

                    # Keep task group alive - consumer.start() will block
                    # Consumer runs in the blocking portal's thread, task group stays in async context
                    try:
                        # This will keep the task group alive forever (or until cancelled)
                        await anyio.sleep_forever()
                    except anyio.get_cancelled_exc_class():
                        Logger.base.info('✅ [Booking Service] Task group shutting down')

            # Start task group in background
            portal.start_task_soon(run_with_task_group)  # type: ignore
            Logger.base.info('🔄 [Booking Service] Background task group started')

            # Setup signal handlers
            def shutdown_handler(signum, frame):
                Logger.base.info(f'🛑 [Booking Service] Received signal {signum}')
                consumer.running = False

            signal.signal(signal.SIGINT, shutdown_handler)
            signal.signal(signal.SIGTERM, shutdown_handler)

            try:
                Logger.base.info('✅ [Booking Service] Starting consumer...')
                consumer.start()
            finally:
                try:
                    portal.call(kvrocks_client.disconnect)  # type: ignore
                    Logger.base.info('📡 [Booking Service] Kvrocks disconnected')
                except Exception:
                    pass

                # Shutdown tracing
                tracing.shutdown()
                Logger.base.info('📊 [Booking Service] Tracing shutdown complete')

    run_with_portal()


if __name__ == '__main__':
    main()
