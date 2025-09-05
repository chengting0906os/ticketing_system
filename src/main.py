"""Main FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.shared.config import settings
from src.shared.database import create_db_and_tables
from src.user.port.user_controller import auth_router, users_router
from src.product.port.product_controller import router as product_router
from src.order.port.order_controller import router as order_router


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

# endpoints
app.include_router(auth_router, prefix='/api/auth', tags=['auth'])
app.include_router(users_router, prefix='/api/users', tags=['users'])
app.include_router(product_router, prefix='/api/products', tags=['products'])
app.include_router(order_router, prefix='/api/orders', tags=['orders'])


@app.get('/')
async def root():
    """Root endpoint."""
    return {'message': 'Shopping System API'}
