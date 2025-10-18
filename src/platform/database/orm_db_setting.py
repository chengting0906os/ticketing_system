"""
SQLAlchemy async engine and session management with Read-Write Separation

This module provides:
1. AsyncEngineManager: Manages separate read/write engines with event loop awareness
2. Legacy global engine/session_maker (for backward compatibility)
3. Database class (for new code with proper dependency injection)

Read-Write Separation:
- Write operations: Always use primary database
- Read operations: Use read replica if configured, otherwise fall back to primary
- Transaction consistency: Within UoW, all operations use write session

Configuration:
- POSTGRES_REPLICA_SERVER: Optional read replica hostname
- POSTGRES_REPLICA_PORT: Optional read replica port
- If not configured, all operations use primary database
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from src.platform.logging.loguru_io import Logger

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.platform.config.core_setting import settings


# =============================================================================
# Event-loop-aware Engine Manager
# =============================================================================


class AsyncEngineManager:
    """
    Manages SQLAlchemy async engines with event loop awareness.

    Supports read-write separation:
    - Write engine: connects to primary database
    - Read engine: connects to read replica (falls back to primary if not configured)

    Ensures engines are always bound to the current event loop to prevent
    "Task got Future attached to a different loop" errors.
    """

    def __init__(self):
        self._write_engine: Optional[AsyncEngine] = None
        self._read_engine: Optional[AsyncEngine] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._write_session_maker: Optional[async_sessionmaker[AsyncSession]] = None
        self._read_session_maker: Optional[async_sessionmaker[AsyncSession]] = None

    def get_engine(self, *, read_only: bool = False) -> AsyncEngine | None:
        """
        Get engine for current event loop, creating new one if needed

        Args:
            read_only: If True, return read engine (replica), otherwise write engine (primary)
        """
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            # No event loop running, create engine without loop tracking
            if read_only:
                if self._read_engine is None:
                    self._read_engine = self._create_read_engine()
                return self._read_engine
            else:
                if self._write_engine is None:
                    self._write_engine = self._create_write_engine()
                return self._write_engine

        # If loop changed, dispose old engines and create new ones
        if self._loop is not current_loop:
            if self._write_engine is not None or self._read_engine is not None:
                Logger.base.warning('🔄 [DB] Event loop changed, disposing old engines...')
                # Note: We can't await dispose() here since this is a sync method
                # The engines will be garbage collected, which is safe
                self._write_engine = None
                self._read_engine = None
                self._write_session_maker = None
                self._read_session_maker = None

            Logger.base.info(f'🔗 [DB] Creating engines for event loop {id(current_loop)}')
            self._write_engine = self._create_write_engine()
            self._read_engine = self._create_read_engine()
            self._loop = current_loop

        return self._read_engine if read_only else self._write_engine

    def get_session_maker(self, *, read_only: bool = False) -> async_sessionmaker[AsyncSession]:
        """
        Get session maker for current event loop

        Args:
            read_only: If True, return read session maker, otherwise write session maker
        """
        # Ensure engines are current
        self.get_engine(read_only=read_only)

        # Create session maker if needed
        if read_only:
            if self._read_session_maker is None:
                self._read_session_maker = async_sessionmaker(
                    self._read_engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                )
            return self._read_session_maker
        else:
            if self._write_session_maker is None:
                self._write_session_maker = async_sessionmaker(
                    self._write_engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                )
            return self._write_session_maker

    def _create_write_engine(self) -> AsyncEngine:
        """
        Create new async engine for write operations (primary database)

        Uses smaller pool size since writes are less frequent than reads.
        Pool configuration is centralized in settings for easy tuning.
        """
        return create_async_engine(
            settings.DATABASE_URL_ASYNC,
            echo=False,
            future=True,
            pool_size=settings.DB_POOL_SIZE_WRITE,
            max_overflow=settings.DB_POOL_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_recycle=settings.DB_POOL_RECYCLE,
            pool_pre_ping=settings.DB_POOL_PRE_PING,
        )

    def _create_read_engine(self) -> AsyncEngine:
        """
        Create new async engine for read operations (replica database)

        Uses larger pool size to handle read-heavy workloads.
        Falls back to primary if replica not configured.
        Pool configuration is centralized in settings for easy tuning.
        """
        return create_async_engine(
            settings.DATABASE_READ_URL_ASYNC,
            echo=False,
            future=True,
            pool_size=settings.DB_POOL_SIZE_READ,
            max_overflow=settings.DB_POOL_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_recycle=settings.DB_POOL_RECYCLE,
            pool_pre_ping=settings.DB_POOL_PRE_PING,
        )


# Global engine manager
_engine_manager = AsyncEngineManager()


# =============================================================================
# Legacy global accessor functions (for backward compatibility)
# =============================================================================


def get_engine(*, read_only: bool = False) -> AsyncEngine | None:
    """Get event-loop-aware engine (read_only: use replica if available)"""
    return _engine_manager.get_engine(read_only=read_only)


def get_session_maker(*, read_only: bool = False) -> async_sessionmaker[AsyncSession]:
    """Get event-loop-aware session maker (read_only: use replica if available)"""
    return _engine_manager.get_session_maker(read_only=read_only)


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
        # pyrefly: ignore  # missing-attribute
        async with current_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, checkfirst=True)
    except Exception as e:
        error_msg = str(e).lower()
        if any(
            keyword in error_msg
            for keyword in ['already exists', 'duplicate key', 'unique constraint']
        ):
            Logger.base.info('Tables already exist, skipping creation')
        else:
            Logger.base.error(f'Error creating tables: {e}')
            raise


# =============================================================================
# Session Provider (for FastAPI Depends injection)
# =============================================================================


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide async session for dependency injection (write operations)

    Note: The async_session_maker() context manager automatically:
    - Handles session cleanup on exit
    - Rolls back on exception
    - Uses event-loop-aware engine to prevent loop conflicts
    """
    session_maker = get_session_maker(read_only=False)
    async with session_maker() as session:
        yield session


async def get_async_read_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide async read-only session for dependency injection (read operations from replica)

    Falls back to primary database if replica is not configured.

    Note: The async_session_maker() context manager automatically:
    - Handles session cleanup on exit
    - Rolls back on exception
    - Uses event-loop-aware engine to prevent loop conflicts
    """
    session_maker = get_session_maker(read_only=True)
    async with session_maker() as session:
        yield session


# =============================================================================
# Database Class (for new code with DI)
# =============================================================================


class Database:
    """
    Database class for dependency injection pattern using AsyncEngineManager

    Delegates to AsyncEngineManager for event-loop-aware engine management
    and read-write separation support.
    """

    def __init__(self, *, read_only: bool = False) -> None:
        """
        Initialize Database with engine manager

        Args:
            read_only: If True, use read replica engine; otherwise use write engine
        """
        self._read_only = read_only
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Context manager for database sessions

        Uses AsyncEngineManager to get event-loop-aware session maker.
        Supports read-write separation based on read_only flag.

        Note: Automatically handles rollback on exception
        """
        # Get session maker from global engine manager (event-loop-aware)
        session_maker = get_session_maker(read_only=self._read_only)
        async with session_maker() as session:
            yield session
