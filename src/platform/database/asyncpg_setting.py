"""
asyncpg connection pool management

This module provides high-performance bulk operations using asyncpg's native
COPY protocol, which is significantly faster than SQLAlchemy for bulk inserts.

Usage:
    pool = await get_asyncpg_pool()
    async with pool.acquire() as conn:
        await conn.copy_records_to_table('table_name', records=data)
"""

import asyncpg

from src.platform.config.core_setting import settings

# Global connection pool (singleton pattern)
asyncpg_pool: asyncpg.Pool | None = None


async def get_asyncpg_pool() -> asyncpg.Pool:
    """
    Get or create asyncpg connection pool for COPY operations

    Returns:
        asyncpg.Pool: Connection pool for high-performance operations
    """
    global asyncpg_pool
    if asyncpg_pool is None:
        # Convert SQLAlchemy URL to asyncpg format
        dsn = settings.DATABASE_URL_ASYNC.replace('postgresql+asyncpg://', 'postgresql://')

        asyncpg_pool = await asyncpg.create_pool(
            dsn,
            min_size=settings.ASYNCPG_POOL_MIN_SIZE,
            max_size=settings.ASYNCPG_POOL_MAX_SIZE,
            command_timeout=settings.ASYNCPG_POOL_COMMAND_TIMEOUT,
        )
    return asyncpg_pool


async def close_asyncpg_pool():
    """Close the asyncpg connection pool"""
    global asyncpg_pool
    if asyncpg_pool:
        await asyncpg_pool.close()
        asyncpg_pool = None
