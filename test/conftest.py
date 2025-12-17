"""
Test Configuration and Fixtures

This module provides:
- Database setup and cleanup for parallel testing (pytest-xdist)
- Kvrocks isolation with worker-specific key prefixes
- Test fixtures for users, events, and tickets
- BDD step definitions (imported from bdd_steps_loader.py)
- Service fixtures (imported from fixture_loader.py)

Architecture:
- Unit tests (test/**/unit/): Override fixtures with mocks in their own conftest.py
- Integration tests: Use real DB/Kvrocks with proper cleanup
"""

# =============================================================================
# CRITICAL: Environment setup MUST happen before any other imports
# This ensures KVROCKS_KEY_PREFIX and POSTGRES_DB are set before modules
# that read them at import time (e.g., key_str_generator.py, settings)
# =============================================================================
import os
from pathlib import Path


def _early_setup_test_environment() -> None:
    """Set test environment variables before any module imports.

    This must run at the top of conftest.py, before importing any application
    modules that read environment variables at import time.
    """
    # Set test database and kvrocks prefix based on xdist worker
    worker_id = os.environ.get('PYTEST_XDIST_WORKER', 'master')
    if worker_id == 'master':
        os.environ['POSTGRES_DB'] = 'ticketing_system_test_db'
        os.environ['KVROCKS_KEY_PREFIX'] = 'test_'
    else:
        os.environ['POSTGRES_DB'] = f'ticketing_system_test_db_{worker_id}'
        os.environ['KVROCKS_KEY_PREFIX'] = f'test_{worker_id}_'

    # Create test log directory
    test_log_dir = Path(__file__).parent / 'test_log'
    test_log_dir.mkdir(exist_ok=True)
    os.environ['TEST_LOG_DIR'] = str(test_log_dir)

    # Pool size settings for tests
    os.environ.setdefault('DB_POOL_SIZE_WRITE', '2')
    os.environ.setdefault('DB_POOL_SIZE_READ', '2')
    os.environ.setdefault('DB_POOL_MAX_OVERFLOW', '2')
    os.environ.setdefault('ASYNCPG_POOL_MIN_SIZE', '5')
    os.environ.setdefault('ASYNCPG_POOL_MAX_SIZE', '10')

    # Replace kvrocks client with test client BEFORE any modules import it
    # This MUST happen before wildcard imports that might load modules using kvrocks_client
    import src.platform.state.kvrocks_client
    from test.kvrocks_test_client import kvrocks_test_client_async

    src.platform.state.kvrocks_client.kvrocks_client = kvrocks_test_client_async


# Call immediately to set env vars before any imports
_early_setup_test_environment()

import asyncio  # noqa: E402
from collections.abc import AsyncGenerator, Callable, Generator  # noqa: E402
import contextlib  # noqa: E402
from typing import Any  # noqa: E402

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from test.shared.utils import create_user  # noqa: E402
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
# Pytest Hooks: Detect test type and setup accordingly
# =============================================================================
def _is_unit_test_only_run(config: pytest.Config) -> bool:
    markexpr = config.getoption('markexpr', default='')
    if markexpr and 'unit' in str(markexpr):
        return True

    args = config.args or []
    test_paths = [arg for arg in args if arg and not arg.startswith('-')]
    return bool(test_paths and all('/unit/' in path or '\\unit\\' in path for path in test_paths))


def pytest_configure(config: pytest.Config) -> None:
    if _is_unit_test_only_run(config):
        return

    _setup_integration_environment()

    worker_id = os.environ.get('PYTEST_XDIST_WORKER', 'master')
    if worker_id != 'master':
        asyncio.run(_setup_test_database())


def pytest_sessionstart(session: pytest.Session) -> None:
    if _is_unit_test_only_run(session.config):
        return

    if os.environ.get('PYTEST_XDIST_WORKER', 'master') == 'master':
        asyncio.run(_setup_test_database())


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        markers = [m.name for m in item.iter_markers()]
        if 'unit' not in markers:
            item.fixturenames.extend(['clean_kvrocks', 'clean_database'])


# =============================================================================
# Integration Environment Setup (kvrocks client replacement only)
# Environment variables are already set by _early_setup_test_environment()
# =============================================================================
_integration_initialized = False


def _setup_integration_environment() -> None:
    """Replace kvrocks client with test client for integration tests.

    NOTE: Environment variables (POSTGRES_DB, KVROCKS_KEY_PREFIX, etc.) are set
    by _early_setup_test_environment() at module load time, before any imports.
    This function only handles the kvrocks client replacement.
    """
    global _integration_initialized
    if _integration_initialized:
        return
    _integration_initialized = True

    # Replace kvrocks client with test client
    import src.platform.state.kvrocks_client
    from test.kvrocks_test_client import kvrocks_test_client_async

    src.platform.state.kvrocks_client.kvrocks_client = kvrocks_test_client_async


# =============================================================================
# Database Configuration
# =============================================================================
def _get_db_config() -> dict[str, str]:
    env_file = '.env' if Path('.env').exists() else '.env.example'
    load_dotenv(env_file)

    return {
        'user': os.getenv('POSTGRES_USER', 'postgres'),
        'password': os.getenv('POSTGRES_PASSWORD', 'postgres'),
        'host': os.getenv('POSTGRES_SERVER', 'localhost'),
        'port': os.getenv('POSTGRES_PORT', '5432'),
        'test_db': os.getenv('POSTGRES_DB', 'ticketing_system_test_db'),
    }


def _get_test_database_url() -> str:
    """Get test database URL"""
    cfg = _get_db_config()
    return (
        f'postgresql+asyncpg://{cfg["user"]}:{cfg["password"]}'
        f'@{cfg["host"]}:{cfg["port"]}/{cfg["test_db"]}'
    )


_cached_tables: list[str] | None = None


# =============================================================================
# Database Setup and Cleanup
# =============================================================================
async def _setup_test_database() -> None:
    db_url = _get_test_database_url()
    cfg = _get_db_config()

    # Create database if not exists
    postgres_url = db_url.replace(f'/{cfg["test_db"]}', '/postgres')
    engine = create_async_engine(postgres_url, isolation_level='AUTOCOMMIT')
    async with engine.begin() as conn:
        result = await conn.execute(
            text(f"SELECT 1 FROM pg_database WHERE datname = '{cfg['test_db']}'")
        )
        if not result.fetchone():
            await conn.execute(text(f'CREATE DATABASE {cfg["test_db"]}'))
    await engine.dispose()

    # Reset schema and run migrations
    reset_engine = create_async_engine(db_url)
    async with reset_engine.begin() as conn:
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
    await reset_engine.dispose()

    alembic_cfg = Config(Path(__file__).parent.parent / 'alembic.ini')
    alembic_cfg.set_main_option('sqlalchemy.url', db_url.replace('+asyncpg', ''))
    command.upgrade(alembic_cfg, 'head')


async def _clean_all_tables() -> None:
    global _cached_tables
    engine = create_async_engine(_get_test_database_url())
    try:
        async with engine.begin() as conn:
            if _cached_tables is None:
                result = await conn.execute(
                    text(
                        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                        "AND tablename != 'alembic_version'"
                    )
                )
                _cached_tables = [row[0] for row in result]

            if _cached_tables:
                quoted = [f'"{t}"' for t in _cached_tables]
                try:
                    await conn.execute(
                        text(f'TRUNCATE {", ".join(quoted)} RESTART IDENTITY CASCADE')
                    )
                except Exception as e:
                    if 'does not exist' in str(e):
                        _cached_tables = None
                    else:
                        raise
    finally:
        await engine.dispose()


# =============================================================================
# Integration Test Fixtures
# =============================================================================
@pytest.fixture(scope='function')
async def clean_kvrocks() -> AsyncGenerator[None, None]:
    from src.platform.state.kvrocks_client import kvrocks_client

    await kvrocks_client.initialize()
    key_prefix = os.getenv('KVROCKS_KEY_PREFIX', 'test_')
    client = kvrocks_client.get_client()

    keys: list[str] = await client.keys(f'{key_prefix}*')  # type: ignore
    if keys:
        await client.delete(*keys)

    yield

    keys_after: list[str] = await client.keys(f'{key_prefix}*')  # type: ignore
    if keys_after:
        await client.delete(*keys_after)


@pytest.fixture(scope='function')
async def clean_database() -> AsyncGenerator[None, None]:
    await _clean_all_tables()
    yield

    from src.platform.database.asyncpg_setting import close_asyncpg_pool
    from src.platform.database.orm_db_setting import _engine_manager

    try:
        current_loop = asyncio.get_running_loop()
        current_loop_id = id(current_loop)
    except RuntimeError:
        current_loop_id = None

    if current_loop_id and _engine_manager._loop and id(_engine_manager._loop) == current_loop_id:
        if _engine_manager._write_engine:
            await _engine_manager._write_engine.dispose()
            _engine_manager._write_engine = None
            _engine_manager._write_session_maker = None
        if _engine_manager._read_engine:
            await _engine_manager._read_engine.dispose()
            _engine_manager._read_engine = None
            _engine_manager._read_session_maker = None
        _engine_manager._loop = None

    with contextlib.suppress(Exception):
        await close_asyncpg_pool()


# =============================================================================
# Session-scoped Fixtures
# =============================================================================
@pytest.fixture(scope='session')
def client() -> Generator[Any, None, None]:
    from test.test_main import app

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clear_client_cookies(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    # Skip for unit tests - they don't use the HTTP client
    if 'unit' in [m.name for m in request.node.iter_markers()]:
        yield
        return
    # Lazily get client to avoid creating it for unit tests
    client = request.getfixturevalue('client')
    client.cookies.clear()
    yield
    client.cookies.clear()


@pytest.fixture(scope='session')
def seller_user(client: Any) -> dict[str, Any]:
    created = create_user(client, TEST_SELLER_EMAIL, DEFAULT_PASSWORD, TEST_SELLER_NAME, 'seller')
    return created or {
        'id': 1,
        'email': TEST_SELLER_EMAIL,
        'name': TEST_SELLER_NAME,
        'role': 'seller',
    }


@pytest.fixture(scope='session')
def buyer_user(client: Any) -> dict[str, Any]:
    created = create_user(client, TEST_BUYER_EMAIL, DEFAULT_PASSWORD, TEST_BUYER_NAME, 'buyer')
    return created or {'id': 2, 'email': TEST_BUYER_EMAIL, 'name': TEST_BUYER_NAME, 'role': 'buyer'}


@pytest.fixture(scope='session')
def another_buyer_user(client: Any) -> dict[str, Any]:
    created = create_user(
        client, ANOTHER_BUYER_EMAIL, DEFAULT_PASSWORD, ANOTHER_BUYER_NAME, 'buyer'
    )
    return created or {
        'id': 3,
        'email': ANOTHER_BUYER_EMAIL,
        'name': ANOTHER_BUYER_NAME,
        'role': 'buyer',
    }


@pytest.fixture
def execute_sql_statement() -> Callable[..., list[dict[str, Any]] | None]:
    def _execute(
        statement: str, params: dict[str, Any] | None = None, fetch: bool = False
    ) -> list[dict[str, Any]] | None:
        async def _run() -> list[dict[str, Any]] | None:
            engine = create_async_engine(_get_test_database_url())
            async with engine.begin() as conn:
                result = await conn.execute(text(statement), params or {})
                if fetch:
                    return [dict(row._mapping) for row in result]
            await engine.dispose()
            return None

        return asyncio.run(_run())

    return _execute


# =============================================================================
# Load BDD steps and service fixtures
# =============================================================================
from test.bdd_steps_loader import *  # noqa: E402, F401, F403
from test.fixture_loader import *  # noqa: E402, F401, F403
