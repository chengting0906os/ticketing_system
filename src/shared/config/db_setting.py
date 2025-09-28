from typing import AsyncGenerator

import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.shared.config.core_setting import settings


engine = create_async_engine(
    settings.DATABASE_URL_ASYNC,
    echo=False,
    future=True,
    # Connection pool settings for high-performance bulk operations
    pool_size=50,  # 常駐連線數
    max_overflow=50,  # 額外連線數
    pool_timeout=30,  # 取得連線超時
    pool_recycle=3600,  # 連線回收時間 (1小時)
    pool_pre_ping=True,  # 連線前測試
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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
