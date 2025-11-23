"""
Standalone Seat Reservation Consumer Entry Point

Usage:
    PYTHONPATH=$PWD uv run python src/service/seat_reservation/driving_adapter/start_seat_reservation_consumer.py
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
from src.platform.state.lua_script_executor import lua_script_executor
from src.service.seat_reservation.driving_adapter.seat_reservation_mq_consumer import (
    SeatReservationConsumer,
)


def main() -> None:
    Logger.base.info('🚀 [Standalone Seat Reservation Consumer] Starting...')

    # Setup OpenTelemetry tracing
    tracing = TracingConfig(service_name='reservation-service')
    tracing.setup()
    Logger.base.info('📊 [Standalone Seat Reservation Consumer] OpenTelemetry configured')

    # Get event ID from environment
    event_id = int(os.getenv('EVENT_ID', '1'))

    # Auto-create topics before consumer starts
    topic_initializer = KafkaTopicInitializer()
    topic_initializer.ensure_topics_exist(event_id=event_id)
    Logger.base.info(
        f'📝 [Standalone Seat Reservation Consumer] Topics ensured for EVENT_ID={event_id}'
    )

    consumer = SeatReservationConsumer()

    def run_with_portal() -> None:
        """Run consumer in thread with BlockingPortal for async-to-sync calls"""
        with start_blocking_portal() as portal:
            consumer.set_portal(portal)

            # Initialize Kvrocks for consumer event loop
            try:
                client = portal.call(kvrocks_client.initialize)  # type: ignore
                Logger.base.info('📡 [Standalone Seat Reservation Consumer] Kvrocks initialized')

                # Initialize Lua scripts
                portal.call(lambda: lua_script_executor.initialize(client=client))  # type: ignore
                Logger.base.info('🔥 [Standalone Seat Reservation Consumer] Lua scripts loaded')
            except Exception as e:
                Logger.base.error(
                    f'❌ [Standalone Seat Reservation Consumer] Failed to initialize Kvrocks/Lua: {e}'
                )
                raise

            # Create and inject task group for fire-and-forget event publishing
            # We need to keep the task group alive during consumer execution
            async def run_with_task_group():
                async with anyio.create_task_group() as tg:
                    # Inject task group into DI container
                    container.task_group.override(tg)
                    Logger.base.info(
                        '🔄 [Standalone Seat Reservation Consumer] Task group injected into DI container'
                    )

                    # Keep task group alive - consumer.start() will block
                    # We'll use a cancellation scope to allow shutdown
                    # Consumer runs in the blocking portal's thread, task group stays in async context
                    try:
                        # This will keep the task group alive forever (or until cancelled)
                        await anyio.sleep_forever()
                    except anyio.get_cancelled_exc_class():
                        Logger.base.info(
                            '✅ [Standalone Seat Reservation Consumer] Task group shutting down'
                        )

            # Start task group in background
            portal.start_task_soon(run_with_task_group)  # type: ignore
            Logger.base.info(
                '🔄 [Standalone Seat Reservation Consumer] Background task group started'
            )

            # Setup signal handlers
            def shutdown_handler(signum, frame):
                Logger.base.info(
                    f'🛑 [Standalone Seat Reservation Consumer] Received signal {signum}'
                )
                consumer.running = False

            signal.signal(signal.SIGINT, shutdown_handler)
            signal.signal(signal.SIGTERM, shutdown_handler)

            try:
                Logger.base.info('✅ [Standalone Seat Reservation Consumer] Starting consumer...')
                consumer.start()
            finally:
                try:
                    portal.call(kvrocks_client.disconnect)  # type: ignore
                    Logger.base.info(
                        '📡 [Standalone Seat Reservation Consumer] Kvrocks disconnected'
                    )
                except Exception:
                    pass

                # Shutdown tracing
                tracing.shutdown()
                Logger.base.info(
                    '📊 [Standalone Seat Reservation Consumer] Tracing shutdown complete'
                )

    run_with_portal()


if __name__ == '__main__':
    main()
