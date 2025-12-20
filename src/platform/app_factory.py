"""
Shared FastAPI App Factory

Provides common app setup for production and test environments.
Extracts shared configuration to reduce code duplication.
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from src.platform.config.core_setting import settings
from src.platform.exception.exception_handlers import register_exception_handlers
from src.platform.observability.tracing import TracingConfig
from src.service.ticketing.driving_adapter.http_controller.booking_controller import (
    router as booking_router,
)
from src.service.ticketing.driving_adapter.http_controller.event_ticketing_controller import (
    router as event_router,
)
from src.service.ticketing.driving_adapter.http_controller.user_controller import (
    router as auth_router,
)


def create_app(
    *,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[Any]],
    title_suffix: str = '',
    description: str = 'Unified Ticketing System',
    service_name: str = 'ticketing-service',
) -> FastAPI:
    """
    Create a configured FastAPI application.

    Args:
        lifespan: Async context manager for app lifespan (startup/shutdown)
        title_suffix: Optional suffix for app title (e.g., " (Test)")
        description: App description
        service_name: Service name for tracing

    Returns:
        Configured FastAPI application
    """
    title = f'{settings.PROJECT_NAME}{title_suffix}'

    app = FastAPI(
        title=title,
        description=description,
        version=settings.VERSION,
        lifespan=lifespan,
    )

    # Auto-instrument FastAPI (must be done before mounting routes)
    tracing_config = TracingConfig(service_name=service_name)
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

    # Register common endpoints
    _register_common_endpoints(app)

    return app


def _register_common_endpoints(app: FastAPI) -> None:
    """Register health and metrics endpoints."""

    @app.get('/health')
    async def health_check() -> dict[str, str]:
        """Health check endpoint for container orchestration."""
        return {'status': 'healthy', 'service': 'Ticketing System'}

    @app.get('/metrics')
    async def get_metrics() -> PlainTextResponse:
        """Prometheus metrics endpoint."""
        return PlainTextResponse(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
