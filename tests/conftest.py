import asyncio
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


# Override POSTGRES_DB environment variable to use a dedicated test database
# Support pytest-xdist parallel testing with different database per worker
worker_id = os.environ.get('PYTEST_XDIST_WORKER', 'master')
if worker_id == 'master':
    os.environ['POSTGRES_DB'] = 'ticketing_system_test_db'
else:
    # Each worker gets its own database
    os.environ['POSTGRES_DB'] = f'ticketing_system_test_db_{worker_id}'

# Override LOG_DIR to use test log directory
test_log_dir = Path(__file__).parent / 'test_log'
test_log_dir.mkdir(exist_ok=True)
os.environ['TEST_LOG_DIR'] = str(test_log_dir)

from src.main import app  # noqa: E402
from tests.booking.integration.fixtures import *  # noqa: E402, F403
from tests.booking.integration.steps.given import *  # noqa: E402, F403
from tests.booking.integration.steps.then import *  # noqa: E402, F403
from tests.booking.integration.steps.when import *  # noqa: E402, F403
from tests.event_ticketing.integration.fixtures import *  # noqa: E402, F403
from tests.event_ticketing.integration.steps.given import *  # noqa: E402, F403
from tests.event_ticketing.integration.steps.then import *  # noqa: E402, F403
from tests.event_ticketing.integration.steps.when import *  # noqa: E402, F403
from tests.pytest_bdd_ng_example.fixtures import *  # noqa: E402, F403
from tests.seat_reservation.integration.fixtures import *  # noqa: E402, F403
from tests.seat_reservation.integration.steps.given import *  # noqa: E402, F403
from tests.seat_reservation.integration.steps.then import *  # noqa: E402, F403
from tests.seat_reservation.integration.steps.when import *  # noqa: E402, F403
from tests.pytest_bdd_ng_example.given import *  # noqa: E402, F403
from tests.pytest_bdd_ng_example.then import *  # noqa: E402, F403
from tests.pytest_bdd_ng_example.when import *  # noqa: E402, F403
from tests.shared.given import *  # noqa: E402, F403
from tests.shared.then import *  # noqa: E402, F403
from tests.shared.utils import create_user  # noqa: E402, F403
from tests.shared_kernel.user.functional.fixtures import *  # noqa: E402, F403
from tests.shared_kernel.user.functional.then import *  # noqa: E402, F403
from tests.shared_kernel.user.functional.when import *  # noqa: E402, F403
from tests.util_constant import (  # noqa: E402, F403
    ANOTHER_BUYER_EMAIL,
    ANOTHER_BUYER_NAME,
    DEFAULT_PASSWORD,
    TEST_BUYER_EMAIL,
    TEST_BUYER_NAME,
    TEST_SELLER_EMAIL,
    TEST_SELLER_NAME,
)


# Load environment variables from .env or .env.example
env_file = '.env' if Path('.env').exists() else '.env.example'
load_dotenv(env_file)

DB_CONFIG = {
    'user': os.getenv('POSTGRES_USER'),
    'password': os.getenv('POSTGRES_PASSWORD'),
    'host': os.getenv('POSTGRES_SERVER'),
    'port': os.getenv('POSTGRES_PORT'),
    'test_db': os.environ['POSTGRES_DB'],  # Use the worker-specific database
}
TEST_DATABASE_URL = f'postgresql+asyncpg://{DB_CONFIG["user"]}:{DB_CONFIG["password"]}@{DB_CONFIG["host"]}:{DB_CONFIG["port"]}/{DB_CONFIG["test_db"]}'


@pytest.fixture
def execute_sql_statement():
    def _execute(statement: str, params: dict | None = None, fetch: bool = False):
        async def _run():
            engine = create_async_engine(TEST_DATABASE_URL)
            async with engine.begin() as conn:
                result = await conn.execute(text(statement), params or {})
                if fetch:
                    return [dict(row._mapping) for row in result]
            await engine.dispose()
            return None

        return asyncio.run(_run())

    return _execute


async def execute_sql(url: str, statements: list, **engine_kwargs):
    engine = create_async_engine(url, **engine_kwargs)
    async with engine.begin() as conn:
        for stmt in statements:
            await conn.execute(text(stmt))
    await engine.dispose()


async def setup_test_database():
    postgres_url = TEST_DATABASE_URL.replace(f'/{DB_CONFIG["test_db"]}', '/postgres')
    engine = create_async_engine(postgres_url, isolation_level='AUTOCOMMIT')
    async with engine.begin() as conn:
        result = await conn.execute(
            text(f"SELECT 1 FROM pg_database WHERE datname = '{DB_CONFIG['test_db']}'")
        )
        if not result.fetchone():
            await conn.execute(text(f'CREATE DATABASE {DB_CONFIG["test_db"]}'))
    await engine.dispose()
    await execute_sql(TEST_DATABASE_URL, ['DROP SCHEMA public CASCADE', 'CREATE SCHEMA public'])
    alembic_cfg = Config(Path(__file__).parent.parent / 'alembic.ini')
    alembic_cfg.set_main_option('sqlalchemy.url', TEST_DATABASE_URL.replace('+asyncpg', ''))
    command.upgrade(alembic_cfg, 'head')

    await verify_migration_completed()


_cached_tables = None


async def verify_migration_completed():
    """TDD FIX: Verify that migration created all required tables before continuing."""
    required_tables = ['user', 'event', 'booking', 'ticket']
    max_retries = 10
    retry_delay = 0.1  # 100ms delay between retries

    for attempt in range(max_retries):
        try:
            engine = create_async_engine(TEST_DATABASE_URL)
            async with engine.begin() as conn:
                result = await conn.execute(
                    text(
                        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename != 'alembic_version'"
                    )
                )
                existing_tables = [row[0] for row in result]
            await engine.dispose()

            # Check if all required tables exist
            missing_tables = [table for table in required_tables if table not in existing_tables]
            if not missing_tables:
                global _cached_tables
                _cached_tables = existing_tables
                return

            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                raise RuntimeError(
                    f'Migration verification failed: missing tables {missing_tables}. '
                    f'Found tables: {existing_tables}'
                )
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                raise RuntimeError(f'Migration verification failed: {e}')


async def clean_all_tables():
    global _cached_tables
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as conn:
            # TDD FIX: Always refresh table list if not cached, handle missing tables gracefully
            if _cached_tables is None:
                try:
                    result = await conn.execute(
                        text(
                            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename != 'alembic_version'"
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


def pytest_sessionstart(session):
    asyncio.run(setup_test_database())


@pytest.fixture(autouse=True)
async def clean_database():
    await clean_all_tables()
    yield


@pytest.fixture(scope='session')
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clear_client_cookies(client):
    """每個測試前清除 client 的 cookies，避免登入狀態殘留"""
    client.cookies.clear()
    yield
    client.cookies.clear()


@pytest.fixture(scope='session')
def seller_user(client):
    created = create_user(client, TEST_SELLER_EMAIL, DEFAULT_PASSWORD, TEST_SELLER_NAME, 'seller')
    if created:
        return created
    else:
        # User already exists, return user data without login
        return {'id': 1, 'email': TEST_SELLER_EMAIL, 'name': TEST_SELLER_NAME, 'role': 'seller'}


@pytest.fixture(scope='session')
def buyer_user(client):
    # Try to create user first
    created = create_user(client, TEST_BUYER_EMAIL, DEFAULT_PASSWORD, TEST_BUYER_NAME, 'buyer')

    if created:
        return created
    else:
        # User already exists, return user data without login
        return {'id': 2, 'email': TEST_BUYER_EMAIL, 'name': TEST_BUYER_NAME, 'role': 'buyer'}


@pytest.fixture(scope='session')
def another_buyer_user(client):
    created = create_user(
        client, ANOTHER_BUYER_EMAIL, DEFAULT_PASSWORD, ANOTHER_BUYER_NAME, 'buyer'
    )
    if created:
        return created
    else:
        # User already exists, return user data without login
        return {'id': 3, 'email': ANOTHER_BUYER_EMAIL, 'name': ANOTHER_BUYER_NAME, 'role': 'buyer'}


# Common test fixtures for unit tests
@pytest.fixture
def mock_uow():
    """Mock unit of work for testing."""
    from unittest.mock import AsyncMock, Mock

    uow = Mock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    uow.events = Mock()
    uow.events.get_by_id = AsyncMock()
    uow.tickets = Mock()
    uow.tickets.get_by_event_id = AsyncMock()
    uow.tickets.get_available_tickets_by_event = AsyncMock()
    uow.tickets.get_by_event_and_section = AsyncMock()
    uow.tickets.list_by_event_section_and_subsection = AsyncMock()
    return uow


@pytest.fixture
def sample_event():
    """Sample event for testing."""
    from unittest.mock import Mock

    return Mock(id=1, seller_id=1, name='Test Event')


@pytest.fixture
def available_tickets():
    """Sample available tickets for testing."""
    from datetime import datetime

    from src.event_ticketing.domain.event_ticketing_aggregate import Ticket, TicketStatus

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
