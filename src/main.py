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
from pathlib import Path
from typing import TypeVar

import anyio
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


# Generic middleware wrapper to satisfy type checker
T = TypeVar('T', bound=BaseHTTPMiddleware)


def as_middleware(middleware_class: type[T]) -> type[T]:
    """
    Type-safe wrapper for middleware classes.
    Helps Pyre understand that middleware classes are compatible with add_middleware.
    """
    return middleware_class


# NOTE: Consumers are now started independently as standalone processes
# See:
# - src/service/ticketing/driving_adapter/mq_consumer/start_ticketing_consumer.py
# - src/service/seat_reservation/driving_adapter/start_seat_reservation_consumer.py
#
# To start 4 ticketing + 4 seat reservation consumers: make start-consumers


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage unified application lifespan: startup and shutdown"""
    # ============================================================================
    # STARTUP
    # ============================================================================
    Logger.base.info('🚀 [Unified Service] Starting up...')

    # Setup OpenTelemetry tracing
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
        tracing.instrument_sqlalchemy(engine=engine)
        Logger.base.info('🗄️  [Unified Service] Database engine ready + instrumented')

    # Auto-instrument Redis/Kvrocks
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
    Logger.base.info('🔥 [Unified Service] Asyncpg pool warmed up to MAX_SIZE')

    Logger.base.info('✅ [Unified Service] All services initialized')

    # Use async with to manage task group lifecycle
    async with anyio.create_task_group() as background_task_group:
        # Inject task group into DI container for fire-and-forget event publishing
        container.task_group.override(background_task_group)
        Logger.base.info('🔄 [Unified Service] Task group injected into DI container')

        Logger.base.info(
            '💡 [Unified Service] Kafka consumers should be started independently:\n'
            '   - Ticketing: uv run python src/service/ticketing/driving_adapter/mq_consumer/start_ticketing_consumer.py\n'
            '   - Seat Reservation: uv run python src/service/seat_reservation/driving_adapter/start_seat_reservation_consumer.py\n'
            '   - Or use: make c-start'
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
tracing_config = TracingConfig(service_name='unified-ticketing-service')
tracing_config.instrument_fastapi(app=app)

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
