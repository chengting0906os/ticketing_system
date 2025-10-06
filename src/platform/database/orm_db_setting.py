"""
SQLAlchemy async engine and session management

This module provides:
1. Legacy global engine/session_maker (for backward compatibility)
2. Database class (for new code with proper dependency injection)
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.platform.config.core_setting import settings

logger = logging.getLogger(__name__)


# =============================================================================
# Legacy global instances (used by get_async_session and create_db_and_tables)
# TODO: Migrate to Database class
# =============================================================================

engine = create_async_engine(
    settings.DATABASE_URL_ASYNC,
    echo=False,
    future=True,
    pool_size=50,
    max_overflow=50,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# =============================================================================
# Base Model
# =============================================================================


class Base(DeclarativeBase):
    pass


# =============================================================================
# Table Creation
# =============================================================================


async def create_db_and_tables():
    """Create database tables if they don't exist"""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, checkfirst=True)
    except Exception as e:
        error_msg = str(e).lower()
        if any(
            keyword in error_msg
            for keyword in ['already exists', 'duplicate key', 'unique constraint']
        ):
            logger.info('Tables already exist, skipping creation')
        else:
            logger.error(f'Error creating tables: {e}')
            raise


# =============================================================================
# Session Provider (for FastAPI Depends injection)
# =============================================================================


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide async session for dependency injection

    Note: The async_session_maker() context manager automatically:
    - Handles session cleanup on exit
    - Rolls back on exception
    """
    async with async_session_maker() as session:
        yield session


# =============================================================================
# Database Class (for new code with DI)
# =============================================================================


class Database:
    """
    Database class for dependency injection pattern

    Each Database instance manages its own engine and session factory.
    Prefer this over global engine/session_maker for better testability.
    """

    def __init__(self, db_url: str) -> None:
        self._engine = create_async_engine(
            db_url,
            echo=False,
            future=True,
            pool_size=50,
            max_overflow=50,
            pool_timeout=30,
            pool_recycle=3600,
            pool_pre_ping=True,
        )
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Context manager for database sessions

        Note: Automatically handles rollback on exception
        """
        async with self._session_factory() as session:
            yield session
