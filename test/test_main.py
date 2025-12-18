"""
Test-specific FastAPI Application

Simplified version without Kafka consumers and background polling tasks.
Uses shared app factory for common setup.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from src.platform.app_factory import create_app
from src.platform.config.di import container
from src.platform.config.wire_modules import WIRE_MODULES
from src.platform.database.asyncpg_setting import close_all_asyncpg_pools, get_asyncpg_pool
from src.platform.database.orm_db_setting import create_db_and_tables, get_engine
from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.platform.state.lua_script_executor import lua_script_executor


@asynccontextmanager
async def lifespan_for_tests(app: FastAPI) -> AsyncIterator[None]:
    """
    Minimal lifespan for testing - no Kafka consumers, no polling tasks.

    Only initializes essential resources:
    - Dependency injection
    - Database engine
    - Kvrocks connection
    - Asyncpg pool (no warmup for faster startup)
    """
    Logger.base.info('🧪 [Test App] Starting up...')

    # Create database tables if they don't exist
    await create_db_and_tables()
    Logger.base.info('🗄️  [Test App] Database tables created')

    # Wire dependency injection for all modules
    container.wire(modules=WIRE_MODULES)
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
    mock_task_group = MagicMock()
    mock_task_group.start_soon = MagicMock()
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


# Create FastAPI app using shared factory
app = create_app(
    lifespan=lifespan_for_tests,
    title_suffix=' (Test)',
    description='Test Application - No Kafka consumers or background tasks',
    service_name='test-ticketing-service',
)


@app.get('/')
async def root() -> RedirectResponse:
    """Root endpoint - redirect to static index."""
    return RedirectResponse(url='/static/index.html')
