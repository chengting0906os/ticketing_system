"""
Test-specific FastAPI Application
Simplified version without Kafka consumers and background polling tasks.

This module provides a FastAPI app specifically for testing that:
- Excludes Kafka consumers (no background message processing)
- Excludes polling tasks (no background database queries)
- Includes all HTTP routes for API testing
- Minimal lifespan for faster test startup
"""

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from src.platform.config.core_setting import settings
from src.platform.config.di import container
from src.platform.database.asyncpg_setting import close_all_asyncpg_pools, get_asyncpg_pool
from src.platform.database.orm_db_setting import create_db_and_tables, get_engine
from src.platform.exception.exception_handlers import register_exception_handlers
from src.platform.logging.loguru_io import Logger
from src.platform.observability.tracing import TracingConfig

# Use monkey-patched test client from conftest.py
from src.platform.state.kvrocks_client import kvrocks_client
from src.platform.state.lua_script_executor import lua_script_executor

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


@asynccontextmanager
async def lifespan_for_tests(app: FastAPI):
    """
    Minimal lifespan for testing - no Kafka consumers, no polling tasks.

    Only initializes essential resources:
    - Dependency injection
    - Database engine
    - Kvrocks connection
    - Asyncpg pool (optional warmup)
    """
    Logger.base.info('🧪 [Test App] Starting up...')

    # Create database tables if they don't exist
    await create_db_and_tables()
    Logger.base.info('🗄️  [Test App] Database tables created')

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
    Logger.base.info('🔌 [Test App] Dependency injection wired')

    # Initialize database
    engine = get_engine()
    if engine:
        Logger.base.info('🗄️  [Test App] Database engine ready')

    # Initialize Kvrocks connection pool (fail-fast)
    await kvrocks_client.initialize()
    Logger.base.info('📡 [Test App] Kvrocks initialized')

    # Initialize Lua scripts
    client = kvrocks_client.get_client()
    await lua_script_executor.initialize(client=client)
    Logger.base.info('🔧 [Test App] Lua scripts initialized')

    # Initialize asyncpg connection pool (skip warmup for faster test startup)
    await get_asyncpg_pool()
    Logger.base.info('🏊 [Test App] Asyncpg pool initialized')

    # Create mock task group for fire-and-forget event publishing (tests only)
    # Use mock instead of real anyio task_group to avoid event loop issues in tests
    mock_task_group = MagicMock()
    mock_task_group.start_soon = MagicMock()

    # Inject mock task group into DI container
    container.task_group.override(mock_task_group)
    Logger.base.info('🔄 [Test App] Mock task group injected into DI container')

    Logger.base.info('✅ [Test App] Startup complete (no Kafka, no polling)')

    yield

    # Shutdown
    Logger.base.info('🛑 [Test App] Shutting down...')

    # Close asyncpg pools
    await close_all_asyncpg_pools()
    Logger.base.info('🏊 [Test App] Asyncpg pools closed')

    # Disconnect Kvrocks
    await kvrocks_client.disconnect()
    Logger.base.info('📡 [Test App] Kvrocks disconnected')

    # Unwire DI
    container.unwire()

    Logger.base.info('👋 [Test App] Shutdown complete')


# Create FastAPI app for testing
app = FastAPI(
    title=f'{settings.PROJECT_NAME} (Test)',
    description='Test Application - No Kafka consumers or background tasks',
    version=settings.VERSION,
    lifespan=lifespan_for_tests,
)

# Auto-instrument FastAPI (must be done before mounting routes)
tracing_config = TracingConfig(service_name='test-ticketing-service')
tracing_config.instrument_fastapi(app=app)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,  # type: ignore
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
    """Root endpoint - redirect to static index"""
    return RedirectResponse(url='/static/index.html')


@app.get('/health')
async def health_check():
    """Health check endpoint for container orchestration"""
    return {'status': 'healthy', 'service': 'Test Ticketing System'}


@app.get('/metrics')
async def get_metrics():
    """Prometheus metrics endpoint"""
    return PlainTextResponse(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
