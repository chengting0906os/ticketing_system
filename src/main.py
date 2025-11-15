"""
Unified Ticketing System - Main Application
Combines Ticketing Service and Seat Reservation Service into a single process.

This unified architecture provides:
- Single deployment unit for easier operations
- Shared resource pools (database, Kvrocks) for efficiency
- Unified observability and tracing
- Lower operational overhead
"""

from contextlib import asynccontextmanager
import os
from pathlib import Path
import signal
from typing import TypeVar

import anyio
from anyio.from_thread import start_blocking_portal
import anyio.to_thread
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from src.platform.config.core_setting import settings
from src.platform.config.di import container
from src.platform.database.asyncpg_setting import (
    close_all_asyncpg_pools,
    get_asyncpg_pool,
    warmup_asyncpg_pool,
)
from src.platform.database.orm_db_setting import get_engine
from src.platform.exception.exception_handlers import register_exception_handlers
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.event_publisher import flush_all_messages
from src.platform.message_queue.kafka_topic_initializer import KafkaTopicInitializer
from src.platform.observability.tracing import TracingConfig
from src.platform.state.kvrocks_client import kvrocks_client

# Seat Reservation Service imports
from src.service.seat_reservation.driving_adapter.seat_reservation_controller import (
    router as seat_reservation_router,
)

# Ticketing Service imports
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

# Ticketing MQ Consumer imports (for background task)
from src.service.ticketing.driving_adapter.mq_consumer.ticketing_mq_consumer import (
    TicketingMqConsumer,
)


# Generic middleware wrapper to satisfy type checker
T = TypeVar('T', bound=BaseHTTPMiddleware)


def as_middleware(middleware_class: type[T]) -> type[T]:
    """
    Type-safe wrapper for middleware classes.
    Helps Pyre understand that middleware classes are compatible with add_middleware.
    """
    return middleware_class


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage unified application lifespan: startup and shutdown"""
    # ============================================================================
    # STARTUP
    # ============================================================================
    Logger.base.info('🚀 [Unified Service] Starting up...')

    # Setup OpenTelemetry tracing (environment-aware: Jaeger local, X-Ray AWS)
    tracing = TracingConfig(service_name='unified-ticketing-service')
    tracing.setup()
    Logger.base.info('📊 [Unified Service] OpenTelemetry tracing configured')

    # Wire dependency injection for all modules
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
    Logger.base.info('🔌 [Unified Service] Dependency injection wired')

    # Initialize database
    engine = get_engine()
    if engine:
        if tracing:
            tracing.instrument_sqlalchemy(engine=engine)
        Logger.base.info('🗄️  [Unified Service] Database engine ready + instrumented')

    # Auto-instrument Redis/Kvrocks
    if tracing:
        tracing.instrument_redis()
        Logger.base.info('📊 [Unified Service] Redis instrumentation configured')

    # Initialize Kvrocks connection pool (fail-fast)
    await kvrocks_client.initialize()
    Logger.base.info('📡 [Unified Service] Kvrocks initialized')

    # Initialize asyncpg connection pool (eager initialization)
    await get_asyncpg_pool()
    Logger.base.info('🏊 [Unified Service] Asyncpg pool initialized')

    # Warmup pool to eliminate "connect" spans during request handling
    await warmup_asyncpg_pool()
    Logger.base.info('🔥 [Unified Service] Asyncpg pool warmed up to MIN_SIZE')

    # Get event ID from environment for consumer topic initialization
    event_id = int(os.getenv('EVENT_ID', '1'))

    # Auto-create Kafka topics before consumers start
    topic_initializer = KafkaTopicInitializer()
    topic_initializer.ensure_topics_exist(event_id=event_id)
    Logger.base.info(f'📝 [Unified Service] Kafka topics ensured for EVENT_ID={event_id}')

    Logger.base.info('✅ [Unified Service] All services initialized')

    # ========== Start Ticketing Consumer in Background (Shared Process) ==========
    # IMPORTANT: Running in same process ensures Singleton cache is shared!
    # When consumer receives Kafka events and calls update_cache(), it updates
    # the same cache instance that API service uses for availability checks

    # Get shared seat_availability_cache from DI container (Singleton)
    seat_availability_cache = container.seat_availability_query_handler()

    # Get event broadcaster for consumer
    event_broadcaster = container.booking_event_broadcaster()

    # Create ticketing consumer with shared cache
    ticketing_consumer = TicketingMqConsumer(
        event_broadcaster=event_broadcaster,
        seat_availability_cache=seat_availability_cache,
    )

    Logger.base.info('🎫 [Unified Service] Starting Ticketing Consumer in background...')

    # Define consumer runner with BlockingPortal (required for async callbacks)
    def run_with_portal(*args: object, **kwargs: object) -> None:
        """Run ticketing consumer with BlockingPortal for async-to-sync calls"""

        with start_blocking_portal() as portal:
            ticketing_consumer.set_portal(portal)

            # Create and inject task group for fire-and-forget event publishing
            # We need to keep the task group alive during consumer execution
            async def run_with_task_group() -> None:
                async with anyio.create_task_group() as tg:
                    # Inject task group into DI container
                    container.task_group.override(tg)
                    Logger.base.info('🔄 [Unified Service] Task group injected into DI container')

                    # Keep task group alive - consumer.start() will block
                    # Consumer runs in the blocking portal's thread, task group stays in async context
                    try:
                        # This will keep the task group alive forever (or until cancelled)
                        await anyio.sleep_forever()
                    except anyio.get_cancelled_exc_class():
                        Logger.base.info('✅ [Unified Service] Task group shutting down')

            # Start task group in background
            portal.start_task_soon(run_with_task_group)  # type: ignore
            Logger.base.info('🔄 [Unified Service] Background task group started')

            # Setup signal handlers
            def shutdown_handler(signum: int, frame: object) -> None:
                Logger.base.info(f'🛑 [Unified Service] Received signal {signum}')
                ticketing_consumer.running = False

            signal.signal(signal.SIGINT, shutdown_handler)
            signal.signal(signal.SIGTERM, shutdown_handler)

            try:
                Logger.base.info('✅ [Unified Service] Starting consumer...')
                ticketing_consumer.start()
            finally:
                Logger.base.info('🛑 [Unified Service] Consumer stopped')

    # Use async with to manage background task lifecycle
    async with anyio.create_task_group() as background_task_group:
        # Start consumer in background thread (consumer.start() is blocking)
        # Use to_thread.run_sync to run blocking code without blocking the event loop
        async def start_consumer(*args: object, **kwargs: object) -> None:
            await anyio.to_thread.run_sync(run_with_portal)  # type: ignore[arg-type]

        background_task_group.start_soon(start_consumer)  # type: ignore[arg-type]

        Logger.base.info(
            '✅ [Unified Service] Ticketing Consumer started (integrated with API service)\n'
            '   💡 Seat Reservation Consumer should still run independently:\n'
            '      - uv run python src/service/seat_reservation/driving_adapter/start_seat_reservation_consumer.py'
        )

        Logger.base.info('✅ [Unified Service] All background tasks started')

        # Yield inside async with - FastAPI will keep running until shutdown
        # When shutdown is triggered, async with will automatically cancel task group
        yield

    # Task group automatically cancelled and cleaned up by async with above
    Logger.base.info('🛑 [Unified Service] All background tasks stopped')

    # ============================================================================
    # SHUTDOWN
    # ============================================================================
    Logger.base.info('🛑 [Unified Service] Shutting down...')

    # Flush all pending Kafka messages before shutdown
    try:
        remaining = flush_all_messages(timeout=5.0)
        if remaining > 0:
            Logger.base.warning(
                f'⚠️  [Unified Service] {remaining} messages not delivered before shutdown'
            )
    except Exception as e:
        Logger.base.error(f'❌ [Unified Service] Failed to flush Kafka messages: {e}')

    # Close asyncpg pools
    await close_all_asyncpg_pools()
    Logger.base.info('🏊 [Unified Service] Asyncpg pools closed')

    # Disconnect Kvrocks
    await kvrocks_client.disconnect()
    Logger.base.info('📡 [Unified Service] Kvrocks disconnected')

    # Shutdown tracing (flush remaining spans)
    if tracing:
        tracing.shutdown()
        Logger.base.info('📊 [Unified Service] Tracing shutdown complete')

    # Unwire DI
    container.unwire()

    Logger.base.info('👋 [Unified Service] Shutdown complete')


# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    description='Unified Ticketing System - Handles user authentication, event management, booking, and seat reservation',
    version=settings.VERSION,
    lifespan=lifespan,
)

# Auto-instrument FastAPI (must be done before mounting routes)
# Note: This creates auto-spans for all HTTP requests (path, method, status, duration)
tracing_config = TracingConfig(service_name='unified-ticketing-service')
tracing_config.instrument_fastapi(app=app)
Logger.base.info('📊 [Unified Service] FastAPI auto-instrumentation enabled')

# Add CORS middleware
app.add_middleware(
    as_middleware(CORSMiddleware),
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Register exception handlers
register_exception_handlers(app)

# Static files
static_dir = Path('static')
if not static_dir.exists():
    static_dir.mkdir(exist_ok=True)
app.mount('/static', StaticFiles(directory='static'), name='static')

# Include routers (all services)
app.include_router(auth_router, prefix='/api/user', tags=['user'])
app.include_router(event_router, prefix='/api/event', tags=['event'])
app.include_router(booking_router, prefix='/api/booking', tags=['booking'])
app.include_router(seat_reservation_router)  # Already has /api/reservation prefix


@app.get('/')
async def root():
    return RedirectResponse(url='/static/index.html')


@app.get('/health')
async def health_check():
    return {'status': 'healthy', 'service': 'Unified Ticketing System'}


@app.get('/metrics')
async def get_metrics():
    return PlainTextResponse(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
