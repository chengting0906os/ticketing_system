"""
SQLAlchemy async engine and session management

This module provides:
1. Legacy global engine/session_maker (for backward compatibility)
2. Database class (for new code with proper dependency injection)
"""

import asyncio
from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.platform.config.core_setting import settings


logger = logging.getLogger(__name__)


# =============================================================================
# Event-loop-aware Engine Manager
# =============================================================================


class AsyncEngineManager:
    """
    Manages SQLAlchemy async engine with event loop awareness.

    Ensures engine is always bound to the current event loop to prevent
    "Task got Future attached to a different loop" errors.
    """

    def __init__(self):
        self._engine: Optional[AsyncEngine] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._session_maker: Optional[async_sessionmaker[AsyncSession]] = None

    def get_engine(self) -> AsyncEngine | None:
        """Get engine for current event loop, creating new one if needed"""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            # No event loop running, create engine without loop tracking
            if self._engine is None:
                self._engine = self._create_engine()
            return self._engine

        # If loop changed, dispose old engine and create new one
        if self._loop is not current_loop:
            if self._engine is not None:
                logger.warning('🔄 [DB] Event loop changed, disposing old engine...')
                # Note: We can't await dispose() here since this is a sync method
                # The engine will be garbage collected, which is safe
                self._engine = None
                self._session_maker = None

            logger.info(f'🔗 [DB] Creating engine for event loop {id(current_loop)}')
            self._engine = self._create_engine()
            self._loop = current_loop

        return self._engine

    def get_session_maker(self) -> async_sessionmaker[AsyncSession]:
        """Get session maker for current event loop"""
        # Ensure engine is current
        self.get_engine()

        # Create session maker if needed
        if self._session_maker is None:
            self._session_maker = async_sessionmaker(
                self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

        return self._session_maker

    def _create_engine(self) -> AsyncEngine:
        """Create new async engine"""
        return create_async_engine(
            settings.DATABASE_URL_ASYNC,
            echo=False,
            future=True,
            pool_size=50,
            max_overflow=50,
            pool_timeout=30,
            pool_recycle=3600,
            pool_pre_ping=True,
        )


# Global engine manager
_engine_manager = AsyncEngineManager()


# =============================================================================
# Legacy global accessor functions (for backward compatibility)
# =============================================================================


def get_engine() -> AsyncEngine | None:
    """Get event-loop-aware engine"""
    return _engine_manager.get_engine()


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get event-loop-aware session maker"""
    return _engine_manager.get_session_maker()


# Backward compatibility: expose as module-level callables
engine = get_engine
async_session_maker = get_session_maker


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
        current_engine = get_engine()
        async with current_engine.begin() as conn:
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
    - Uses event-loop-aware engine to prevent loop conflicts
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
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
