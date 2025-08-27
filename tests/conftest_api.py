"""Configuration for API tests with test database."""

import asyncio
import os

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


# Override environment variables for testing
os.environ["POSTGRES_DB"] = "test_ticketing_db"

from src.main import app
from src.shared.database import Base, get_async_session


# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://py_arch_lab:py_arch_lab@localhost:5432/test_ticketing_db"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Clean up
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture(scope="function")
async def test_session(test_engine):
    """Create test database session."""
    async_session_maker = async_sessionmaker(
        test_engine, 
        class_=AsyncSession, 
        expire_on_commit=False
    )
    
    async with async_session_maker() as session:
        yield session


@pytest.fixture(scope="function")
def test_client(test_session):
    """Create test client with test database."""
    
    async def override_get_async_session():
        yield test_session
    
    # Override the dependency
    app.dependency_overrides[get_async_session] = override_get_async_session
    
    with TestClient(app) as client:
        yield client
    
    # Clear overrides
    app.dependency_overrides.clear()
