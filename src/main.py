from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.order.port.order_controller import router as order_router
from src.event.port.event_controller import router as event_router
from src.ticket.port.ticket_controller import (
    router as ticket_router,
    ticket_router as ticket_operations_router,
)
from src.shared.config.core_setting import settings
from src.shared.config.db_setting import create_db_and_tables
from src.shared.exception.exception_handlers import register_exception_handlers
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

# endpoints
app.include_router(auth_router, prefix='/api/auth', tags=['auth'])
app.include_router(users_router, prefix='/api/user', tags=['user'])
app.include_router(event_router, prefix='/api/event', tags=['event'])
app.include_router(order_router, prefix='/api/order', tags=['order'])
app.include_router(ticket_router, prefix='/api/ticket', tags=['ticket'])
app.include_router(ticket_operations_router, prefix='/api', tags=['ticket-operations'])


@app.get('/')
async def root():
    return {'message': 'Ticketing System API'}
