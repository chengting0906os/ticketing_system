from contextlib import asynccontextmanager
from typing import AsyncGenerator
import logging

import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.shared.config.core_setting import settings

logger = logging.getLogger(__name__)


# Legacy engine and session maker - used by create_db_and_tables() and get_async_session()
# TODO: Migrate these functions to use Database class
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

# asyncpg connection pool for high-performance bulk operations
asyncpg_pool = None


async def get_asyncpg_pool():
    """Get or create asyncpg connection pool for COPY operations"""
    global asyncpg_pool
    if asyncpg_pool is None:
        # Convert SQLAlchemy URL to asyncpg format (remove +asyncpg driver specification)
        dsn = settings.DATABASE_URL_ASYNC.replace('postgresql+asyncpg://', 'postgresql://')

        asyncpg_pool = await asyncpg.create_pool(
            dsn,
            min_size=5,  # Minimum connections in pool
            max_size=20,  # Maximum connections in pool
            command_timeout=60,  # Command timeout in seconds
        )
    return asyncpg_pool


async def close_asyncpg_pool():
    """Close the asyncpg connection pool"""
    global asyncpg_pool
    if asyncpg_pool:
        await asyncpg_pool.close()
        asyncpg_pool = None


class Base(DeclarativeBase):
    pass


async def create_db_and_tables():
    """Create database tables if they don't exist, with better error handling"""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, checkfirst=True)
    except Exception as e:
        # Log but don't fail if tables already exist (e.g., created by Alembic)
        error_msg = str(e).lower()
        if any(
            keyword in error_msg
            for keyword in ['already exists', 'duplicate key', 'unique constraint']
        ):
            logger.info('Tables already exist, skipping creation')
        else:
            logger.error(f'Error creating tables: {e}')
            raise


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


class Database:
    """Database class for managing async sessions following dependency-injector best practices"""

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
        """Context manager for database sessions"""
        async with self._session_factory() as session:
            try:
                yield session
            except Exception:
                logger.exception('Session rollback because of exception')
                await session.rollback()
                raise
            finally:
                await session.close()
