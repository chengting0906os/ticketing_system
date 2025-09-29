from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.booking.port.booking_controller import router as booking_router
from src.event_ticketing.port.event_ticketing_controller import router as event_router
from src.seat_reservation.port.seat_reservation_controller import router as seat_reservation_router
from src.shared.config.core_setting import settings
from src.shared.config.db_setting import create_db_and_tables
from src.shared.config.di import cleanup, container, setup
from src.shared.exception.exception_handlers import register_exception_handlers
from src.shared.logging.loguru_io import Logger
from src.shared_kernel.user.port.user_controller import router as auth_router


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
            'src.booking.use_case.command.create_booking_use_case',
            'src.booking.use_case.command.update_booking_status_to_cancelled_use_case',
            'src.booking.use_case.command.update_booking_status_to_paid_use_case',
            'src.booking.use_case.command.update_booking_status_to_pending_payment_use_case',
            'src.booking.use_case.command.update_booking_status_to_failed_use_case',
            'src.booking.use_case.command.mock_payment_and_update_status_to_completed_use_case',
            'src.booking.use_case.query.list_bookings_use_case',
            'src.booking.use_case.query.get_booking_use_case',
            'src.event_ticketing.use_case.command.create_event_use_case',
            'src.event_ticketing.use_case.command.reserve_tickets_use_case',
            'src.event_ticketing.use_case.query.list_events_use_case',
            'src.event_ticketing.use_case.query.get_event_use_case',
            'src.shared_kernel.user.port.user_controller',
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
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Register exception handlers
register_exception_handlers(app)

# Static files
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
