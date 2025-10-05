from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.service.ticketing.driving_adapter.http_controller.booking_controller import (
    router as booking_router,
)
from src.service.ticketing.driving_adapter.http_controller.event_ticketing_controller import (
    router as event_router,
)
from src.platform.config.core_setting import settings
from src.platform.config.db_setting import create_db_and_tables
from src.platform.config.di import cleanup, container, setup
from src.platform.exception.exception_handlers import register_exception_handlers
from src.platform.logging.loguru_io import Logger
from src.service.seat_reservation.driving_adapter.seat_reservation_controller import (
    router as seat_reservation_router,
)
from src.service.ticketing.driving_adapter.http_controller.user_controller import (
    router as auth_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    import os

    if os.getenv('SKIP_DB_INIT', '').lower() not in ('true', '1'):
        await create_db_and_tables()
    setup()

    # Wire the container for dependency injection
    container.wire(
        modules=[
            'src.service.ticketing.app.command.create_booking_use_case',
            'src.service.ticketing.app.command.update_booking_status_to_cancelled_use_case',
            'src.service.ticketing.app.command.update_booking_status_to_paid_use_case',
            'src.service.ticketing.app.command.update_booking_status_to_pending_payment_use_case',
            'src.service.ticketing.app.command.update_booking_status_to_failed_use_case',
            'src.service.ticketing.app.command.mock_payment_and_update_status_to_completed_use_case',
            'src.service.ticketing.app.query.list_bookings_use_case',
            'src.service.ticketing.app.query.get_booking_use_case',
            'src.service.ticketing.app.command.create_event_use_case',
            'src.service.ticketing.app.command.reserve_tickets_use_case',
            'src.service.ticketing.app.query.list_events_use_case',
            'src.service.ticketing.app.query.get_event_use_case',
            'src.service.ticketing.driving_adapter.http_controller.user_controller',
        ]
    )

    yield

    try:
        cleanup()
    except Exception as e:
        # Log but don't fail the shutdown

        Logger.base.warning(f'Error during cleanup: {e}')


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


@app.get('/')
async def root():
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url='/static/index.html')
