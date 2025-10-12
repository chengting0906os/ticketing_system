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

    Supports dual engine mode:
    - Writer engine: For INSERT/UPDATE/DELETE operations
    - Reader engine: For SELECT operations (Aurora read replicas)
    """

    def __init__(self, db_url: str, is_read_replica: bool = False):
        """
        Initialize engine manager

        Args:
            db_url: Database connection URL
            is_read_replica: If True, this engine connects to read replicas
        """
        self._db_url = db_url
        self._is_read_replica = is_read_replica
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
        engine_type = 'READ' if self._is_read_replica else 'WRITE'
        logger.info(f'🔗 [DB] Creating {engine_type} engine: {self._db_url.split("@")[-1]}')

        return create_async_engine(
            self._db_url,
            echo=False,
            future=True,
            pool_size=100,
            max_overflow=100,
            pool_timeout=30,
            pool_recycle=3600,
            pool_pre_ping=True,
        )


# Global engine managers (singleton pattern)
_writer_engine_manager = AsyncEngineManager(settings.DATABASE_URL_ASYNC, is_read_replica=False)
_reader_engine_manager = AsyncEngineManager(settings.DATABASE_READ_URL_ASYNC, is_read_replica=True)


# =============================================================================
# Legacy global accessor functions (for backward compatibility)
# =============================================================================


def get_engine() -> AsyncEngine | None:
    """Get event-loop-aware writer engine (default for backward compatibility)"""
    return _writer_engine_manager.get_engine()


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get event-loop-aware writer session maker (default for backward compatibility)"""
    return _writer_engine_manager.get_session_maker()


# New: Read replica accessors
def get_read_engine() -> AsyncEngine | None:
    """Get event-loop-aware reader engine (for SELECT operations)"""
    return _reader_engine_manager.get_engine()


def get_read_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get event-loop-aware reader session maker (for SELECT operations)"""
    return _reader_engine_manager.get_session_maker()


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
    Provide async WRITER session for dependency injection

    Use this for endpoints that perform writes (INSERT/UPDATE/DELETE).

    Note: The async_session_maker() context manager automatically:
    - Handles session cleanup on exit
    - Rolls back on exception
    - Uses event-loop-aware engine to prevent loop conflicts
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
        yield session


async def get_async_read_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide async READER session for dependency injection

    Use this for read-only endpoints that only perform SELECT queries.
    Routes traffic to Aurora read replicas for better performance.

    Note: Falls back to writer endpoint if POSTGRES_READ_SERVER not configured.
    """
    session_maker = get_read_session_maker()
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
            max_overflow=150,
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
