"""
Test Configuration and Fixtures

This module provides:
- Database setup and cleanup for parallel testing (pytest-xdist)
- Kvrocks isolation with worker-specific key prefixes
- Test fixtures for users, events, and tickets
- BDD step definitions (imported from bdd_steps_loader.py)
- Service fixtures (imported from fixture_loader.py)

Note: For adding new BDD steps or fixtures, update the respective loader modules
instead of this file to maintain a clean separation of concerns.
"""

import asyncio
import contextlib
import os
from collections.abc import AsyncGenerator, Callable, Generator
from pathlib import Path
from typing import Any
from unittest.mock import Mock

from redis import Redis as SyncRedis

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


# =============================================================================
# Environment Setup for Parallel Testing
# =============================================================================
# Each pytest-xdist worker gets isolated database and Kvrocks namespace
worker_id = os.environ.get('PYTEST_XDIST_WORKER', 'master')
if worker_id == 'master':
    os.environ['POSTGRES_DB'] = 'ticketing_system_test_db'
    os.environ['KVROCKS_KEY_PREFIX'] = 'test_'
else:
    # Worker-specific isolation
    os.environ['POSTGRES_DB'] = f'ticketing_system_test_db_{worker_id}'
    os.environ['KVROCKS_KEY_PREFIX'] = f'test_{worker_id}_'

# Test log directory
test_log_dir = Path(__file__).parent / 'test_log'
test_log_dir.mkdir(exist_ok=True)
os.environ['TEST_LOG_DIR'] = str(test_log_dir)

# =============================================================================
# Monkey-patch production kvrocks_client with test version
# =============================================================================
# Replace production client with test client that supports per-event-loop connections
# This must happen BEFORE any imports that use kvrocks_client
import src.platform.state.kvrocks_client  # noqa: E402
from test.kvrocks_test_client import kvrocks_test_client_async  # noqa: E402


src.platform.state.kvrocks_client.kvrocks_client = kvrocks_test_client_async

# =============================================================================
# Database Connection Pool Configuration for Tests
# =============================================================================
# Override pool settings to prevent connection exhaustion during parallel testing
# With 10 workers × (1 write + 1 read) × (2 pool + 2 overflow) = 80 connections
# Plus asyncpg: 10 workers × 5 min = 50 connections
# Total: 130 connections (within PostgreSQL's 200 limit)
os.environ['DB_POOL_SIZE_WRITE'] = '2'
os.environ['DB_POOL_SIZE_READ'] = '2'
os.environ['DB_POOL_MAX_OVERFLOW'] = '2'
os.environ['ASYNCPG_POOL_MIN_SIZE'] = '5'
os.environ['ASYNCPG_POOL_MAX_SIZE'] = '10'

# =============================================================================
# Import Application and Test Components
# =============================================================================
# Import test-specific app (no Kafka consumers, no polling tasks)
# Import all BDD steps and service fixtures through consolidated modules
from test.bdd_steps_loader import *  # noqa: E402, F403
from test.fixture_loader import *  # noqa: E402, F403

# Explicit imports for commonly used test utilities
from test.shared.utils import create_user  # noqa: E402
from test.test_main import app  # noqa: E402
from test.util_constant import (  # noqa: E402
    ANOTHER_BUYER_EMAIL,
    ANOTHER_BUYER_NAME,
    DEFAULT_PASSWORD,
    TEST_BUYER_EMAIL,
    TEST_BUYER_NAME,
    TEST_SELLER_EMAIL,
    TEST_SELLER_NAME,
)


# =============================================================================
# Database Configuration
# =============================================================================
env_file = '.env' if Path('.env').exists() else '.env.example'
load_dotenv(env_file)

DB_CONFIG = {
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', 'postgres'),
    'host': os.getenv('POSTGRES_SERVER', 'localhost'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'test_db': os.getenv('POSTGRES_DB', 'ticketing_system'),
}
TEST_DATABASE_URL = (
    f'postgresql+asyncpg://{DB_CONFIG["user"]}:{DB_CONFIG["password"]}'
    f'@{DB_CONFIG["host"]}:{DB_CONFIG["port"]}/{DB_CONFIG["test_db"]}'
)

# Cache for table names to avoid repeated queries
_cached_tables = None


# =============================================================================
# Database Setup and Cleanup
# =============================================================================
async def setup_test_database() -> None:
    """Create test database and run migrations"""
    # Create database if not exists
    postgres_url = TEST_DATABASE_URL.replace(f'/{DB_CONFIG["test_db"]}', '/postgres')
    engine = create_async_engine(postgres_url, isolation_level='AUTOCOMMIT')
    async with engine.begin() as conn:
        result = await conn.execute(
            text(f"SELECT 1 FROM pg_database WHERE datname = '{DB_CONFIG['test_db']}'")
        )
        if not result.fetchone():
            await conn.execute(text(f'CREATE DATABASE {DB_CONFIG["test_db"]}'))
    await engine.dispose()

    # Reset schema and run migrations
    await execute_sql(TEST_DATABASE_URL, ['DROP SCHEMA public CASCADE', 'CREATE SCHEMA public'])
    alembic_cfg = Config(Path(__file__).parent.parent / 'alembic.ini')
    alembic_cfg.set_main_option('sqlalchemy.url', TEST_DATABASE_URL.replace('+asyncpg', ''))
    command.upgrade(alembic_cfg, 'head')

    await verify_migration_completed()


async def execute_sql(url: str, statements: list, **engine_kwargs: object) -> None:
    """Execute SQL statements"""
    engine = create_async_engine(url, **engine_kwargs)
    async with engine.begin() as conn:
        for stmt in statements:
            await conn.execute(text(stmt))
    await engine.dispose()


async def verify_migration_completed() -> None:
    """Verify all required tables exist after migration"""
    required_tables = ['user', 'event', 'booking', 'ticket']
    max_retries = 10
    retry_delay = 0.1

    for attempt in range(max_retries):
        try:
            engine = create_async_engine(TEST_DATABASE_URL)
            async with engine.begin() as conn:
                result = await conn.execute(
                    text(
                        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                        "AND tablename != 'alembic_version'"
                    )
                )
                existing_tables = [row[0] for row in result]
            await engine.dispose()

            missing_tables = [t for t in required_tables if t not in existing_tables]
            if not missing_tables:
                global _cached_tables
                _cached_tables = existing_tables
                return

            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                raise RuntimeError(
                    f'Migration failed: missing {missing_tables}. Found: {existing_tables}'
                )
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                raise RuntimeError(f'Migration verification failed: {e}')


async def clean_all_tables() -> None:
    """Truncate all tables for test isolation"""
    global _cached_tables
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as conn:
            # Refresh table list if not cached
            if _cached_tables is None:
                try:
                    result = await conn.execute(
                        text(
                            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                            "AND tablename != 'alembic_version'"
                        )
                    )
                    _cached_tables = [row[0] for row in result]
                except Exception:
                    _cached_tables = []

            if _cached_tables:
                quoted_tables = [f'"{table}"' for table in _cached_tables]
                try:
                    await conn.execute(
                        text(f'TRUNCATE {", ".join(quoted_tables)} RESTART IDENTITY CASCADE')
                    )
                except Exception as e:
                    if 'does not exist' in str(e):
                        _cached_tables = None
                    else:
                        raise
    finally:
        await engine.dispose()


# =============================================================================
# Pytest Hooks for Parallel Testing
# =============================================================================
def pytest_sessionstart(session: pytest.Session) -> None:
    """Setup database in master process (runs once before workers spawn)"""
    # Skip DB setup for unit-only tests (set SKIP_DB_SETUP=1)
    if os.environ.get('SKIP_DB_SETUP') == '1':
        return
    if os.environ.get('PYTEST_XDIST_WORKER', 'master') == 'master':
        asyncio.run(setup_test_database())


def pytest_configure(config: pytest.Config) -> None:
    """Setup database in each worker process"""
    # Skip DB setup for unit-only tests
    if os.environ.get('SKIP_DB_SETUP') == '1':
        return
    if os.environ.get('PYTEST_XDIST_WORKER', 'master') != 'master':
        asyncio.run(setup_test_database())


# =============================================================================
# Pytest Hook: Auto-apply integration fixtures to non-unit tests
# =============================================================================
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply integration fixtures to tests without @pytest.mark.unit"""
    for item in items:
        markers = [m.name for m in item.iter_markers()]
        if 'unit' not in markers:
            # Add integration fixtures to non-unit tests
            item.fixturenames.extend(['clean_kvrocks', 'clean_database'])


# =============================================================================
# Integration Test Fixtures (auto-applied via pytest hook)
# =============================================================================
@pytest.fixture(scope='function')
async def clean_kvrocks() -> AsyncGenerator[None, None]:
    """
    Clean Kvrocks before and after each test

    Uses the monkey-patched kvrocks_client (async version).
    Auto-applied to non-unit tests via pytest_collection_modifyitems hook.
    """
    from src.platform.state.kvrocks_client import kvrocks_client

    # Initialize for current event loop (required for per-loop test client)
    await kvrocks_client.initialize()

    # Clean Kvrocks data before test
    key_prefix = os.getenv('KVROCKS_KEY_PREFIX', 'test_')
    client = kvrocks_client.get_client()
    keys: list[str] = await client.keys(f'{key_prefix}*')  # type: ignore
    if keys:
        await client.delete(*keys)

    yield

    # Cleanup after test
    keys_after: list[str] = await client.keys(f'{key_prefix}*')  # type: ignore
    if keys_after:
        await client.delete(*keys_after)


@pytest.fixture(scope='function')
async def clean_database() -> AsyncGenerator[None, None]:
    """
    Clean all database tables and dispose DB engines after each test

    Critical for test isolation - prevents connection pool exhaustion by:
    1. Cleaning tables before test
    2. Disposing SQLAlchemy engines after test (releases all connections)
    3. Closing asyncpg pool after test

    Auto-applied to non-unit tests via pytest_collection_modifyitems hook.
    """
    await clean_all_tables()
    yield

    # Cleanup: Dispose engines to release all DB connections
    # Important: Each pytest-xdist worker has its own process, so this cleanup
    # only affects the current worker's engines, not other workers
    import asyncio

    from src.platform.database.asyncpg_setting import close_asyncpg_pool
    from src.platform.database.orm_db_setting import _engine_manager

    # Get current event loop ID to ensure we only clean up this loop's resources
    try:
        current_loop = asyncio.get_running_loop()
        current_loop_id = id(current_loop)
    except RuntimeError:
        current_loop_id = None

    # Dispose SQLAlchemy engines if they belong to current loop
    if current_loop_id and _engine_manager._loop and id(_engine_manager._loop) == current_loop_id:
        if _engine_manager._write_engine is not None:
            await _engine_manager._write_engine.dispose()
            _engine_manager._write_engine = None
            _engine_manager._write_session_maker = None

        if _engine_manager._read_engine is not None:
            await _engine_manager._read_engine.dispose()
            _engine_manager._read_engine = None
            _engine_manager._read_session_maker = None

        # Reset loop tracking
        _engine_manager._loop = None

    # Close asyncpg pool for current loop only
    with contextlib.suppress(Exception):
        await close_asyncpg_pool()


# =============================================================================
# Session-scoped Fixtures
# =============================================================================
@pytest.fixture(scope='session')
def client() -> Generator[TestClient, None, None]:
    """
    FastAPI TestClient for making HTTP requests.

    raise_server_exceptions=False allows catching 500 errors as HTTP responses
    instead of raising exceptions, enabling proper testing of error handling.
    """
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clear_client_cookies(client: TestClient) -> Generator[None, None, None]:
    """Clear client cookies before/after each test to avoid auth state leakage"""
    client.cookies.clear()
    yield
    client.cookies.clear()


@pytest.fixture(scope='session')
def seller_user(client: TestClient) -> dict[str, Any]:
    """Create test seller user"""
    created = create_user(client, TEST_SELLER_EMAIL, DEFAULT_PASSWORD, TEST_SELLER_NAME, 'seller')
    return created or {
        'id': 1,
        'email': TEST_SELLER_EMAIL,
        'name': TEST_SELLER_NAME,
        'role': 'seller',
    }


@pytest.fixture(scope='session')
def buyer_user(client: TestClient) -> dict[str, Any]:
    """Create test buyer user"""
    created = create_user(client, TEST_BUYER_EMAIL, DEFAULT_PASSWORD, TEST_BUYER_NAME, 'buyer')
    return created or {
        'id': 2,
        'email': TEST_BUYER_EMAIL,
        'name': TEST_BUYER_NAME,
        'role': 'buyer',
    }


@pytest.fixture(scope='session')
def another_buyer_user(client: TestClient) -> dict[str, Any]:
    """Create another test buyer user"""
    created = create_user(
        client, ANOTHER_BUYER_EMAIL, DEFAULT_PASSWORD, ANOTHER_BUYER_NAME, 'buyer'
    )
    return created or {
        'id': 3,
        'email': ANOTHER_BUYER_EMAIL,
        'name': ANOTHER_BUYER_NAME,
        'role': 'buyer',
    }


# =============================================================================
# Unit Test Fixtures
# =============================================================================
@pytest.fixture
def sample_event() -> Mock:
    """Sample event for unit testing"""
    return Mock(id=1, seller_id=1, name='Test Event')


@pytest.fixture
def available_tickets() -> list[Any]:
    """Sample available tickets for unit testing"""
    from datetime import datetime

    from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import (
        Ticket,
        TicketStatus,
    )

    now = datetime.now()
    return [
        Ticket(
            id=1,
            event_id=1,
            section='A',
            subsection=1,
            row=1,
            seat=1,
            price=1000,
            status=TicketStatus.AVAILABLE,
            created_at=now,
            updated_at=now,
        )
    ]


@pytest.fixture
def execute_sql_statement() -> Callable[..., list[dict[str, Any]] | None]:
    """Execute SQL statement with optional parameter binding and result fetching"""

    def _execute(
        statement: str, params: dict[str, Any] | None = None, fetch: bool = False
    ) -> list[dict[str, Any]] | None:
        async def _run() -> list[dict[str, Any]] | None:
            engine = create_async_engine(TEST_DATABASE_URL)
            async with engine.begin() as conn:
                result = await conn.execute(text(statement), params or {})
                if fetch:
                    return [dict(row._mapping) for row in result]
            await engine.dispose()
            return None

        return asyncio.run(_run())

    return _execute


# =============================================================================
# Kvrocks Fixtures for Lua Script Tests
# =============================================================================
@pytest.fixture
def kvrocks_client_sync_for_test() -> Generator[SyncRedis, None, None]:
    """
    Sync Kvrocks client for async tests to avoid event loop conflicts

    Uses sync client in async test context to ensure test verification logic
    is independent from the async operations being tested.
    """
    from test.kvrocks_test_client import kvrocks_test_client

    key_prefix = os.getenv('KVROCKS_KEY_PREFIX', 'test_')

    # Cleanup before test
    client = kvrocks_test_client.connect()
    keys_before: list[str] = client.keys(f'{key_prefix}*')  # type: ignore
    if keys_before:
        client.delete(*keys_before)

    yield client

    # Cleanup after test
    keys_after: list[str] = client.keys(f'{key_prefix}*')  # type: ignore
    if keys_after:
        client.delete(*keys_after)
