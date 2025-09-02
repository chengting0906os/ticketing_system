"""Test configuration with async database cleaning."""
# ruff: noqa: F403, F405

import asyncio
import os

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import NullPool, text
from sqlalchemy.ext.asyncio import create_async_engine


# 設定測試環境變數
os.environ['POSTGRES_DB'] = 'ticketing_test_db'


from src.main import app
from src.shared.database import Base

# Import step definitions for pytest_bdd_ng_example
from tests.pytest_bdd_ng_example.fixtures import *
from tests.pytest_bdd_ng_example.given import *
from tests.pytest_bdd_ng_example.then import *
from tests.pytest_bdd_ng_example.when import *

# Import step definitions for user
from tests.user.functional.fixtures import *
from tests.user.functional.then import *
from tests.user.functional.when import *


# 資料庫 URL
ASYNC_DATABASE_URL = 'postgresql+asyncpg://py_arch_lab:py_arch_lab@localhost:5432/ticketing_test_db'


async def async_clean_tables():
    async_engine = create_async_engine(ASYNC_DATABASE_URL, poolclass=NullPool)

    async with async_engine.begin() as conn:
        result = await conn.execute(
            text("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname = 'public'
            AND tablename != 'alembic_version'
        """)
        )
        tables = [row[0] for row in result]

        if tables:
            await conn.execute(text(f'TRUNCATE {", ".join(tables)} CASCADE'))

    await async_engine.dispose()


async def async_create_tables():
    async_engine = create_async_engine(ASYNC_DATABASE_URL, poolclass=NullPool)

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await async_engine.dispose()


asyncio.run(async_create_tables())


@pytest.fixture(autouse=True)
def clean_database():
    asyncio.run(async_clean_tables())
    yield


@pytest.fixture(scope='session')
def client():
    with TestClient(app) as client:
        yield client
