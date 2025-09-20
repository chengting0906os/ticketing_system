from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.booking.port.booking_controller import router as booking_router
from src.event_ticketing.port.event_controller import router as event_router
from src.shared.config.core_setting import settings
from src.shared.config.db_setting import create_db_and_tables
from src.shared.exception.exception_handlers import register_exception_handlers
from src.shared.port.system_controller import router as system_router
from src.user.port.user_controller import auth_router, users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield


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
app.include_router(auth_router, prefix='/api/auth', tags=['auth'])
app.include_router(users_router, prefix='/api/user', tags=['user'])
app.include_router(event_router, prefix='/api/event', tags=['event'])
app.include_router(booking_router, prefix='/api/booking', tags=['booking'])
app.include_router(system_router, prefix='/api', tags=['system-maintenance'])


@app.get('/')
async def root():
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url='/static/index.html')
