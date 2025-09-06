"""Test configuration with async database cleaning."""
# ruff: noqa: F403, F405

import asyncio
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


# Setup test environment
os.environ['POSTGRES_DB'] = 'shopping_test_db'
from src.main import app
from tests.order.functional.fixtures import *
from tests.order.functional.given import *
from tests.order.functional.then import *
from tests.order.functional.when import *

# Import all BDD step definitions - explicit imports are better than exec
from tests.product.functional.fixtures import *
from tests.product.functional.given import *
from tests.product.functional.then import *
from tests.product.functional.when import *

# Import pytest-bdd-ng shared steps and fixtures
from tests.pytest_bdd_ng_example.fixtures import *
from tests.pytest_bdd_ng_example.given import *
from tests.pytest_bdd_ng_example.then import *
from tests.pytest_bdd_ng_example.when import *

# Import shared test steps first
from tests.shared.then import *
from tests.user.functional.fixtures import *
from tests.user.functional.given import *
from tests.user.functional.then import *
from tests.user.functional.when import *


# Database configuration
DB_CONFIG = {
    'user': 'py_arch_lab',
    'password': 'py_arch_lab',
    'host': 'localhost',
    'port': '5432',
    'test_db': 'shopping_test_db',
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
    """Setup test database with fresh schema using Alembic migrations."""
    postgres_url = TEST_DATABASE_URL.replace(f'/{DB_CONFIG["test_db"]}', '/postgres')

    # Ensure test database exists (check first)
    engine = create_async_engine(postgres_url, isolation_level='AUTOCOMMIT')
    async with engine.begin() as conn:
        result = await conn.execute(
            text(f"SELECT 1 FROM pg_database WHERE datname = '{DB_CONFIG['test_db']}'")
        )
        if not result.fetchone():
            await conn.execute(text(f'CREATE DATABASE {DB_CONFIG["test_db"]}'))
    await engine.dispose()

    # Drop all existing tables
    await execute_sql(TEST_DATABASE_URL, ['DROP SCHEMA public CASCADE', 'CREATE SCHEMA public'])

    # Run test migration
    alembic_cfg = Config(Path(__file__).parent.parent / 'src/shared/alembic/alembic.ini')
    alembic_cfg.set_main_option('sqlalchemy.url', TEST_DATABASE_URL.replace('+asyncpg', ''))
    command.upgrade(alembic_cfg, 'head')


# Cache table names to avoid repeated queries
_cached_tables = None


async def clean_all_tables():
    """Clean all tables while preserving structure.

    Caches table names after first query to reduce database overhead.
    """
    global _cached_tables

    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        if _cached_tables is None:
            result = await conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename != 'alembic_version'"
                )
            )
            _cached_tables = [row[0] for row in result]

        if _cached_tables:
            await conn.execute(
                text(f'TRUNCATE {", ".join(_cached_tables)} RESTART IDENTITY CASCADE')
            )
    await engine.dispose()


def pytest_sessionstart(session):
    """Set up test database once at the start of the test session."""
    asyncio.run(setup_test_database())


@pytest.fixture(autouse=True)
async def clean_database():
    """Clean all tables before each test."""
    await clean_all_tables()
    yield


@pytest.fixture(scope='session')
def client():
    """FastAPI test client."""
    with TestClient(app) as test_client:
        yield test_client
