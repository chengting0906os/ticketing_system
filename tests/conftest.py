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

# Import shared test steps first
from tests.shared.then import *


# Import all BDD step definitions
for module in ['product', 'user', 'order']:
    for step_type in ['fixtures', 'given', 'then', 'when']:
        exec(f"from tests.{module}.functional.{step_type} import *")

# pytest_bdd_ng_example has different structure
for step_type in ['fixtures', 'given', 'then', 'when']:
    exec(f"from tests.pytest_bdd_ng_example.{step_type} import *")


# Database configuration
DB_CONFIG = {
    'user': 'py_arch_lab',
    'password': 'py_arch_lab',
    'host': 'localhost',
    'port': '5432',
    'test_db': 'shopping_test_db'
}
TEST_DATABASE_URL = f"postgresql+asyncpg://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['test_db']}"


async def execute_sql(url: str, statements: list, **engine_kwargs):
    engine = create_async_engine(url, **engine_kwargs)
    async with engine.begin() as conn:
        for stmt in statements:
            await conn.execute(text(stmt))
    await engine.dispose()


async def setup_test_database():
    """Setup test database with fresh schema using Alembic migrations."""
    postgres_url = TEST_DATABASE_URL.replace(f"/{DB_CONFIG['test_db']}", '/postgres')
    
    # Ensure test database exists (check first)
    engine = create_async_engine(postgres_url, isolation_level='AUTOCOMMIT')
    async with engine.begin() as conn:
        result = await conn.execute(
            text(f"SELECT 1 FROM pg_database WHERE datname = '{DB_CONFIG['test_db']}'")
        )
        if not result.fetchone():
            await conn.execute(text(f"CREATE DATABASE {DB_CONFIG['test_db']}"))
    await engine.dispose()
    
    # Drop all existing tables  
    await execute_sql(
        TEST_DATABASE_URL,
        ["DROP SCHEMA public CASCADE", "CREATE SCHEMA public"]
    )
    
    # Run test migration
    alembic_cfg = Config(Path(__file__).parent.parent / "src/shared/alembic/alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("+asyncpg", ""))
    command.upgrade(alembic_cfg, "test_clean_init")


async def clean_all_tables():
    """Clean all tables while preserving structure."""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename != 'alembic_version'")
        )
        if tables := [row[0] for row in result]:
            await conn.execute(text(f'TRUNCATE {", ".join(tables)} RESTART IDENTITY CASCADE'))
    await engine.dispose()


def pytest_sessionstart(session):
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
