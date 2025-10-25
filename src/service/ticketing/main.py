"""
Ticketing Service - Main Application
Handles user authentication, event management, and booking operations.
"""

from contextlib import asynccontextmanager
import signal

import anyio
from anyio.from_thread import start_blocking_portal
import anyio.to_thread
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.platform.config.di import container
from src.platform.database.scylla_setting import (
    close_all_scylla_sessions,
    warmup_scylla_session,
)
from src.platform.logging.loguru_io import Logger
from src.platform.observability.tracing import TracingConfig
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.ticketing.driving_adapter.http_controller import (
    booking_controller,
    event_ticketing_controller,
    user_controller,
)
from src.service.ticketing.driving_adapter.http_controller.booking_controller import (
    router as booking_router,
)
from src.service.ticketing.driving_adapter.http_controller.event_ticketing_controller import (
    router as event_router,
)
from src.service.ticketing.driving_adapter.http_controller.user_controller import (
    router as auth_router,
)
from src.service.ticketing.driving_adapter.mq_consumer.ticketing_mq_consumer import (
    TicketingMqConsumer,
)
from src.service.ticketing.driving_adapter.mq_consumer.seat_reservation_mq_consumer import (
    SeatReservationConsumer,
)
from src.service.ticketing.driving_adapter.http_controller.seat_reservation_controller import (
    router as seat_reservation_router,
)


async def start_ticketing_consumer() -> None:
    """
    Start Ticketing MQ consumer in thread with BlockingPortal.

    This function bridges the async FastAPI app with the sync Kafka consumer
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

    consumer = TicketingMqConsumer()

    async def run_consumer_with_portal() -> None:
        """Run consumer in thread with BlockingPortal for async-to-sync calls"""

        def run_with_portal() -> None:
            # Create BlockingPortal to bridge sync Kafka consumer with async use cases
            with start_blocking_portal() as portal:
                consumer.set_portal(portal)

                # Initialize Kvrocks client for this event loop (consumer's event loop)
                try:
                    portal.call(kvrocks_client.initialize)  # type: ignore
                    Logger.base.info('📡 [Consumer] Kvrocks initialized for consumer event loop')
                except Exception as e:
                    Logger.base.error(f'❌ [Consumer] Failed to initialize Kvrocks: {e}')
                    raise

                # Initialize and warmup ScyllaDB session for consumer event loop
                try:
                    portal.call(warmup_scylla_session)  # type: ignore[arg-type]
                    Logger.base.info(
                        '🔥 [Consumer] ScyllaDB session warmed up for consumer event loop'
                    )
                except Exception as e:
                    Logger.base.error(f'❌ [Consumer] Failed to initialize ScyllaDB session: {e}')
                    raise

                # Mock signal handlers to avoid "signal only works in main thread" error
                original_signal = signal.signal

                def mock_signal(*args: object, **kwargs: object) -> object:
                    return None

                signal.signal = mock_signal  # type: ignore[bad-assignment]
                try:
                    # Run the consumer's sync start method (Quix Streams app.run() is sync)
                    consumer.start()  # Direct call - start() is now sync
                finally:
                    signal.signal = original_signal
                    # Cleanup Kvrocks connection for this event loop
                    try:
                        portal.call(kvrocks_client.disconnect)  # type: ignore
                    except Exception:
                        pass

        await anyio.to_thread.run_sync(run_with_portal)  # type: ignore[bad-argument-type]

    await run_consumer_with_portal()


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

                # Initialize Kvrocks client for this event loop (consumer's event loop)
                try:
                    portal.call(kvrocks_client.initialize)  # type: ignore
                    Logger.base.info('📡 [Consumer] Kvrocks initialized for consumer event loop')
                except Exception as e:
                    Logger.base.error(f'❌ [Consumer] Failed to initialize Kvrocks: {e}')
                    raise

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
                    # Cleanup Kvrocks connection for this event loop
                    try:
                        portal.call(kvrocks_client.disconnect)  # type: ignore
                    except Exception:
                        pass

        await anyio.to_thread.run_sync(run_with_portal)  # type: ignore[bad-argument-type]

    if consumer.kafka_app:
        await run_consumer_with_portal()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Manage application lifespan: startup and shutdown"""
    # Startup
    Logger.base.info('🚀 [Ticketing Service] Starting up...')

    # Setup OpenTelemetry tracing
    tracing = TracingConfig(service_name='ticketing-service')
    tracing.setup()
    Logger.base.info('📊 [Ticketing Service] OpenTelemetry tracing configured')

    # Wire dependency injection for controllers
    wire_modules = [
        booking_controller,
        event_ticketing_controller,
        user_controller,
    ]
    container.wire(modules=wire_modules)
    Logger.base.info('🔌 [Ticketing Service] Dependency injection wired')

    # Auto-instrument Redis/Kvrocks
    tracing.instrument_redis()
    Logger.base.info('📊 [Ticketing Service] Redis instrumentation configured')

    # Initialize Kvrocks connection pool (fail-fast)
    await kvrocks_client.initialize()
    Logger.base.info('📡 [Ticketing Service] Kvrocks initialized')

    # Initialize and warmup ScyllaDB session (eager initialization)
    await warmup_scylla_session()
    Logger.base.info('🔥 [Ticketing Service] ScyllaDB session warmed up')

    # Start Kafka consumer (graceful failure if Kafka unavailable)
    import os

    enable_kafka = os.getenv('ENABLE_KAFKA', 'true').lower() in ('true', '1')

    if enable_kafka:
        try:
            consumer_task = anyio.create_task_group()
            await consumer_task.__aenter__()
            # Start both consumers
            consumer_task.start_soon(start_ticketing_consumer)  # type: ignore[arg-type]
            consumer_task.start_soon(start_seat_reservation_consumer)  # type: ignore[arg-type]
            Logger.base.info(
                '📨 [Ticketing Service] Message queue consumers started (ticketing + seat_reservation)'
            )
        except Exception as e:
            Logger.base.warning(
                f'⚠️  [Ticketing Service] Kafka unavailable at startup: {e}'
                '\n   Continuing without Kafka - messaging features disabled'
            )
            # Create empty task group for cleanup consistency
            consumer_task = anyio.create_task_group()
            await consumer_task.__aenter__()
    else:
        Logger.base.info('⏭️  [Ticketing Service] Kafka disabled (ENABLE_KAFKA=false)')
        # Create empty task group for cleanup consistency
        consumer_task = anyio.create_task_group()
        await consumer_task.__aenter__()

    # Inject background task group into DI container for fire-and-forget operations
    container.background_task_group.override(consumer_task)
    Logger.base.info('🔧 [Ticketing Service] Background task group configured')

    # Start seat availability cache polling
    seat_availability_handler = container.seat_availability_query_handler()
    consumer_task.start_soon(seat_availability_handler.start_polling)  # type: ignore[arg-type]
    Logger.base.info('🔄 [Ticketing Service] Seat availability polling started')

    # Start seat state cache polling
    seat_state_handler = container.seat_state_query_handler()
    consumer_task.start_soon(seat_state_handler.start_polling)  # type: ignore[arg-type]
    Logger.base.info('🔄 [Ticketing Service] Seat state polling started')

    Logger.base.info('✅ [Ticketing Service] Startup complete')

    yield

    # Shutdown
    Logger.base.info('🛑 [Ticketing Service] Shutting down...')

    # Stop consumer
    consumer_task.cancel_scope.cancel()
    await consumer_task.__aexit__(None, None, None)

    # Close ScyllaDB sessions
    await close_all_scylla_sessions()
    Logger.base.info('🗄️ [Ticketing Service] ScyllaDB sessions closed')

    # Disconnect Kvrocks
    await kvrocks_client.disconnect()

    # Shutdown tracing (flush remaining spans)
    tracing.shutdown()
    Logger.base.info('📊 [Ticketing Service] Tracing shutdown complete')

    # Unwire DI
    container.unwire()

    Logger.base.info('👋 [Ticketing Service] Shutdown complete')


# Create FastAPI app
app = FastAPI(
    title='Ticketing Service',
    description='Handles user authentication, event management, and booking operations',
    version='1.0.0',
    lifespan=lifespan,
)

# Auto-instrument FastAPI (must be done before mounting routes)
tracing_config = TracingConfig(service_name='ticketing-service')
tracing_config.instrument_fastapi(app=app)

# Mount static files
app.mount('/static', StaticFiles(directory='static'), name='static')

# Include routers
app.include_router(auth_router, prefix='/api/user', tags=['user'])
app.include_router(event_router, prefix='/api/event', tags=['event'])
app.include_router(booking_router, prefix='/api/booking', tags=['booking'])
app.include_router(seat_reservation_router)  # seat reservation SSE endpoints


# Root endpoint
@app.get('/')
async def root():
    """Root endpoint"""
    return {
        'service': 'Ticketing Service',
        'docs': '/docs',
        'health': '/health',
    }


# Health check endpoint
@app.get('/health')
async def health():
    """Health check"""
    return {'status': 'healthy', 'service': 'Ticketing Service'}
