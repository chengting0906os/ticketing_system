"""
Seat Reservation Service - Main Application
Handles seat allocation and reservation operations via Kvrocks state store.
"""

from contextlib import asynccontextmanager
import signal

import anyio
from anyio.from_thread import start_blocking_portal
import anyio.to_thread
from fastapi import FastAPI

from src.platform.config.di import container
from src.platform.database.orm_db_setting import get_engine
from src.platform.logging.loguru_io import Logger
from src.platform.observability.tracing import TracingConfig
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.seat_reservation.driving_adapter.seat_reservation_controller import (
    router as seat_reservation_router,
)
from src.service.seat_reservation.driving_adapter.seat_reservation_mq_consumer import (
    SeatReservationConsumer,
)


async def start_seat_reservation_consumer() -> None:
    """
    Start Seat Reservation MQ consumer (Quix Streams) with BlockingPortal.

    This function bridges the async FastAPI app with the sync Quix consumer
    using anyio's BlockingPortal pattern.

    Auto-creates required Kafka topics before consumer starts to prevent
    UNKNOWN_TOPIC_OR_PART errors during cold start.
    """
    import os

    from src.platform.message_queue.kafka_topic_initializer import KafkaTopicInitializer

    # Get event_id from environment
    event_id = int(os.getenv('EVENT_ID', '1'))

    # Auto-create topics before consumer starts (container-friendly)
    topic_initializer = KafkaTopicInitializer()
    topic_initializer.ensure_topics_exist(event_id=event_id)

    # Initialize consumer with use cases from DI container
    consumer = SeatReservationConsumer()
    consumer.reserve_seats_use_case = container.reserve_seats_use_case()
    consumer.release_seat_use_case = container.release_seat_use_case()
    consumer.finalize_seat_payment_use_case = container.finalize_seat_payment_use_case()

    # Setup Kafka topics
    consumer._setup_topics()

    async def run_consumer_with_portal() -> None:
        """Run consumer in thread with BlockingPortal for async-to-sync calls"""

        def run_with_portal() -> None:
            # Create BlockingPortal to bridge sync Kafka consumer with async use cases
            with start_blocking_portal() as portal:
                consumer.set_portal(portal)

                # Mock signal handlers to avoid "signal only works in main thread" error
                original_signal = signal.signal

                def mock_signal(*args: object, **kwargs: object) -> object:
                    return None

                signal.signal = mock_signal  # type: ignore[bad-assignment]
                try:
                    if consumer.kafka_app:
                        consumer.kafka_app.run()
                finally:
                    signal.signal = original_signal

        await anyio.to_thread.run_sync(run_with_portal)  # type: ignore[bad-argument-type]

    if consumer.kafka_app:
        await run_consumer_with_portal()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Manage application lifespan: startup and shutdown"""
    # Startup
    Logger.base.info('🚀 [Seat Reservation Service] Starting up...')

    # Setup OpenTelemetry tracing
    tracing = TracingConfig(service_name='seat-reservation-service')
    tracing.setup()
    Logger.base.info('📊 [Seat Reservation Service] OpenTelemetry tracing configured')

    # Initialize database
    engine = get_engine()
    if engine:
        # Auto-instrument SQLAlchemy
        tracing.instrument_sqlalchemy(engine=engine)
        Logger.base.info('🗄️  [Seat Reservation Service] Database engine ready + instrumented')

    # Auto-instrument Redis/Kvrocks
    tracing.instrument_redis()
    Logger.base.info('📊 [Seat Reservation Service] Redis instrumentation configured')

    # Connect to Kvrocks
    await kvrocks_client.connect()
    Logger.base.info('📡 [Seat Reservation Service] Kvrocks connected')

    # Start Kafka consumer
    consumer_task = anyio.create_task_group()
    await consumer_task.__aenter__()
    consumer_task.start_soon(start_seat_reservation_consumer)  # type: ignore[arg-type]
    Logger.base.info('📨 [Seat Reservation Service] Message queue consumer started')

    Logger.base.info('✅ [Seat Reservation Service] Startup complete')

    yield

    # Shutdown
    Logger.base.info('🛑 [Seat Reservation Service] Shutting down...')

    # Stop consumer
    consumer_task.cancel_scope.cancel()
    await consumer_task.__aexit__(None, None, None)

    # Disconnect Kvrocks
    await kvrocks_client.disconnect()

    # Shutdown tracing (flush remaining spans)
    tracing.shutdown()
    Logger.base.info('📊 [Seat Reservation Service] Tracing shutdown complete')

    Logger.base.info('👋 [Seat Reservation Service] Shutdown complete')


# Create FastAPI app
app = FastAPI(
    title='Seat Reservation Service',
    description='Handles seat allocation and reservation operations via Kvrocks',
    version='1.0.0',
    lifespan=lifespan,
)

# Auto-instrument FastAPI (must be done before mounting routes)
tracing_config = TracingConfig(service_name='seat-reservation-service')
tracing_config.instrument_fastapi(app=app)

# Include routers
app.include_router(seat_reservation_router)


# Root endpoint
@app.get('/')
async def root():
    """Root endpoint"""
    return {
        'service': 'Seat Reservation Service',
        'docs': '/docs',
        'health': '/health',
    }


# Health check endpoint
@app.get('/health')
async def health():
    """Health check"""
    return {'status': 'healthy', 'service': 'Seat Reservation Service'}
