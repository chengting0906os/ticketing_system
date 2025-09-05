"""Test configuration with async database cleaning."""
# ruff: noqa: F403, F405

import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


# 設定測試環境變數
os.environ['POSTGRES_DB'] = 'shopping_test_db'

from src.main import app

# Import step definitions for all test modules
from tests.product.functional.fixtures import *
from tests.product.functional.given import *
from tests.product.functional.then import *
from tests.product.functional.when import *
from tests.pytest_bdd_ng_example.fixtures import *
from tests.pytest_bdd_ng_example.given import *
from tests.pytest_bdd_ng_example.then import *
from tests.pytest_bdd_ng_example.when import *
from tests.user.functional.fixtures import *
from tests.user.functional.given import *
from tests.user.functional.then import *
from tests.user.functional.when import *


# Database URLs
POSTGRES_URL = 'postgresql+asyncpg://py_arch_lab:py_arch_lab@localhost:5432/postgres'
TEST_DATABASE_URL = 'postgresql+asyncpg://py_arch_lab:py_arch_lab@localhost:5432/shopping_test_db'


@asynccontextmanager
async def get_db_engine(url: str, **kwargs):
    """Context manager for database engine."""
    engine = create_async_engine(url, **kwargs)
    try:
        yield engine
    finally:
        await engine.dispose()


async def ensure_test_database_exists():
    """Create test database if it doesn't exist."""
    async with get_db_engine(POSTGRES_URL, isolation_level='AUTOCOMMIT') as engine:
        async with engine.begin() as conn:
            result = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = 'shopping_test_db'")
            )
            if not result.fetchone():
                await conn.execute(text("CREATE DATABASE shopping_test_db"))


async def setup_test_database():
    """Setup test database with fresh schema using Alembic migrations."""
    # Ensure database exists
    await ensure_test_database_exists()
    
    # Clean up any existing schema
    async with get_db_engine(TEST_DATABASE_URL) as engine:
        async with engine.begin() as conn:
            # Get all tables and drop them with CASCADE
            result = await conn.execute(
                text("""
                    SELECT tablename FROM pg_tables 
                    WHERE schemaname = 'public'
                """)
            )
            tables = [row[0] for row in result]
            
            # Drop all tables including alembic_version to ensure clean migration
            for table in tables:
                await conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
    
    # Run Alembic migrations to create schema (exactly like production)
    alembic_cfg = Config(Path(__file__).parent.parent / "src/shared/alembic/alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("+asyncpg", ""))
    
    # Create fresh schema with the special test migration
    command.upgrade(alembic_cfg, "test_clean_init")


async def clean_all_tables():
    """Clean all tables while preserving structure."""
    async with get_db_engine(TEST_DATABASE_URL) as engine:
        async with engine.begin() as conn:
            # Get all table names except alembic_version
            result = await conn.execute(
                text("""
                    SELECT tablename FROM pg_tables 
                    WHERE schemaname = 'public'
                    AND tablename != 'alembic_version'
                    ORDER BY tablename
                """)
            )
            tables = [row[0] for row in result]
            
            if tables:
                # TRUNCATE is faster than DELETE and resets sequences
                await conn.execute(text(f'TRUNCATE {", ".join(tables)} RESTART IDENTITY CASCADE'))


def pytest_sessionstart(session):
    """Setup test database before test session starts."""
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
