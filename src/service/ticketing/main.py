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
from src.platform.database.asyncpg_setting import (
    close_all_asyncpg_pools,
    get_asyncpg_pool,
    warmup_asyncpg_pool,
)
from src.platform.database.orm_db_setting import get_engine
from src.platform.logging.loguru_io import Logger
from src.platform.observability.tracing import TracingConfig
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.ticketing.app.command import (
    create_booking_use_case,
    create_event_and_tickets_use_case,
    mock_payment_and_update_booking_status_to_completed_and_ticket_to_paid_use_case,
    update_booking_status_to_cancelled_use_case,
    update_booking_status_to_failed_use_case,
    update_booking_status_to_pending_payment_and_ticket_to_reserved_use_case,
)
from src.service.ticketing.app.query import (
    get_booking_use_case,
    get_event_use_case,
    list_bookings_use_case,
    list_events_use_case,
)
from src.service.ticketing.driving_adapter.http_controller import user_controller
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

                # Initialize and warmup asyncpg pool for consumer event loop
                try:
                    portal.call(get_asyncpg_pool)  # type: ignore[arg-type]
                    Logger.base.info(
                        '🏊 [Consumer] Asyncpg pool initialized for consumer event loop'
                    )
                    portal.call(warmup_asyncpg_pool)  # type: ignore[arg-type]
                    Logger.base.info('🔥 [Consumer] Asyncpg pool warmed up for consumer event loop')
                except Exception as e:
                    Logger.base.error(f'❌ [Consumer] Failed to initialize asyncpg pool: {e}')
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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Manage application lifespan: startup and shutdown"""
    # Startup
    Logger.base.info('🚀 [Ticketing Service] Starting up...')

    # Setup OpenTelemetry tracing
    tracing = TracingConfig(service_name='ticketing-service')
    tracing.setup()
    Logger.base.info('📊 [Ticketing Service] OpenTelemetry tracing configured')

    # Wire dependency injection
    wire_modules = [
        create_booking_use_case,
        update_booking_status_to_cancelled_use_case,
        update_booking_status_to_pending_payment_and_ticket_to_reserved_use_case,
        update_booking_status_to_failed_use_case,
        mock_payment_and_update_booking_status_to_completed_and_ticket_to_paid_use_case,
        list_bookings_use_case,
        get_booking_use_case,
        create_event_and_tickets_use_case,
        list_events_use_case,
        get_event_use_case,
        user_controller,
    ]
    container.wire(modules=wire_modules)
    Logger.base.info('🔌 [Ticketing Service] Dependency injection wired')

    # Initialize database
    engine = get_engine()
    if engine:
        # Auto-instrument SQLAlchemy
        tracing.instrument_sqlalchemy(engine=engine)
        Logger.base.info('🗄️  [Ticketing Service] Database engine ready + instrumented')

    # Auto-instrument Redis/Kvrocks
    tracing.instrument_redis()
    Logger.base.info('📊 [Ticketing Service] Redis instrumentation configured')

    # Initialize Kvrocks connection pool (fail-fast)
    await kvrocks_client.initialize()
    Logger.base.info('📡 [Ticketing Service] Kvrocks initialized')

    # Initialize asyncpg connection pool (eager initialization)
    await get_asyncpg_pool()
    Logger.base.info('🏊 [Ticketing Service] Asyncpg pool initialized')

    # Warmup pool to eliminate "connect" spans during request handling
    await warmup_asyncpg_pool()
    Logger.base.info('🔥 [Ticketing Service] Asyncpg pool warmed up to MAX_SIZE')

    # Start Kafka consumer
    consumer_task = anyio.create_task_group()
    await consumer_task.__aenter__()
    consumer_task.start_soon(start_ticketing_consumer)  # type: ignore[arg-type]
    Logger.base.info('📨 [Ticketing Service] Message queue consumer started')

    Logger.base.info('✅ [Ticketing Service] Startup complete')

    yield

    # Shutdown
    Logger.base.info('🛑 [Ticketing Service] Shutting down...')

    # Stop consumer
    consumer_task.cancel_scope.cancel()
    await consumer_task.__aexit__(None, None, None)

    # Close asyncpg pools
    await close_all_asyncpg_pools()
    Logger.base.info('🏊 [Ticketing Service] Asyncpg pools closed')

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
