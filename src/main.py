from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, RedirectResponse  # type: ignore[attr-defined]
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from src.platform.config.core_setting import settings
from src.platform.config.di import cleanup, container, setup
from src.platform.database.db_setting import create_db_and_tables
from src.platform.exception.exception_handlers import register_exception_handlers
from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.seat_reservation.driving_adapter.seat_reservation_controller import (
    router as seat_reservation_router,
)

# Import modules for dependency injection wiring
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
async def lifespan(app: FastAPI):
    # Startup
    import os

    Logger.base.info('🚀 Starting application...')

    if os.getenv('SKIP_DB_INIT', '').lower() not in ('true', '1'):
        await create_db_and_tables()
    setup()

    # Wire the container for dependency injection
    container.wire(
        modules=[
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
    )

    # Initialize Kvrocks connection pool during startup (fail-fast)
    await kvrocks_client.initialize()
    Logger.base.info('✅ Application startup complete')

    yield

    # Shutdown
    Logger.base.info('🛑 Shutting down application...')

    try:
        await kvrocks_client.disconnect_all()
        Logger.base.info('📡 Kvrocks connections closed')
    except Exception as e:
        Logger.base.warning(f'⚠️ Error closing Kvrocks: {e}')

    try:
        cleanup()
    except Exception as e:
        Logger.base.warning(f'⚠️ Error during cleanup: {e}')


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,  # type: ignore
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Register exception handlers
register_exception_handlers(app)

# Static files (optional, create if not exists)
static_dir = Path('static')
if not static_dir.exists():
    static_dir.mkdir(exist_ok=True)
app.mount('/static', StaticFiles(directory='static'), name='static')

# endpoints
app.include_router(auth_router, prefix='/api/user', tags=['user'])
app.include_router(event_router, prefix='/api/event', tags=['event'])
app.include_router(booking_router, prefix='/api/booking', tags=['booking'])
app.include_router(seat_reservation_router)


@app.get('/health')
async def health_check():
    """Health check endpoint for container orchestration"""
    return {'status': 'healthy'}


@app.get('/metrics')
async def get_metrics():
    """Prometheus metrics endpoint"""
    return PlainTextResponse(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get('/')
async def root():
    return RedirectResponse(url='/static/index.html')
