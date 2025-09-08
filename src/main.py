"""Main FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.order.port.order_controller import router as order_router
from src.product.port.product_controller import router as product_router
from src.shared.config.core_setting import settings
from src.shared.config.db_setting import create_db_and_tables
from src.shared.exception.exception_handlers import register_exception_handlers
from src.user.port.user_controller import auth_router, users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown."""
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
app.include_router(product_router, prefix='/api/product', tags=['product'])
app.include_router(order_router, prefix='/api/order', tags=['order'])


@app.get('/')
async def root():
    """Root endpoint."""
    return {'message': 'Shopping System API'}
