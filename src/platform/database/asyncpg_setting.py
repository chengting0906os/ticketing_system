"""
asyncpg connection pool management

This module provides high-performance bulk operations using asyncpg's native
COPY protocol, which is significantly faster than SQLAlchemy for bulk inserts.

Multi-Event-Loop Support:
- Maintains separate connection pools per event loop
- Supports concurrent services (FastAPI + MQ Consumer)
- Prevents "connection was closed" errors from event loop mismatch

Usage:
    pool = await get_asyncpg_pool()
    async with pool.acquire() as conn:
        await conn.copy_records_to_table('table_name', records=data)
"""

import asyncio

import asyncpg

from src.platform.config.core_setting import settings


# Global connection pools per event loop
asyncpg_pools: dict[int, asyncpg.Pool] = {}
asyncpg_lock = asyncio.Lock()


async def get_asyncpg_pool() -> asyncpg.Pool:
    """
    Get or create asyncpg connection pool for the current event loop

    Connection lifecycle management:
    - max_inactive_connection_lifetime: Recycle idle connections after 5 min
    - max_queries: Recycle connections after 50k queries to prevent memory leaks
    - timeout: Fail fast if pool is exhausted (10s)

    Each event loop gets its own pool to prevent connection errors when
    multiple services (FastAPI + MQ Consumer) run concurrently.

    Returns:
        asyncpg.Pool: Connection pool for high-performance operations
    """
    current_loop = asyncio.get_running_loop()
    loop_id = id(current_loop)

    # Fast path: pool already exists for this loop
    if loop_id in asyncpg_pools:
        return asyncpg_pools[loop_id]

    # Slow path: create new pool (thread-safe)
    async with asyncpg_lock:
        # Double-check after acquiring lock
        if loop_id in asyncpg_pools:
            return asyncpg_pools[loop_id]

        # Convert SQLAlchemy URL to asyncpg format
        dsn = settings.DATABASE_URL_ASYNC.replace('postgresql+asyncpg://', 'postgresql://')

        pool = await asyncpg.create_pool(
            dsn,
            min_size=settings.ASYNCPG_POOL_MIN_SIZE,
            max_size=settings.ASYNCPG_POOL_MAX_SIZE,
            command_timeout=settings.ASYNCPG_POOL_COMMAND_TIMEOUT,
            max_inactive_connection_lifetime=settings.ASYNCPG_POOL_MAX_INACTIVE_LIFETIME,
            timeout=settings.ASYNCPG_POOL_TIMEOUT,
            max_queries=settings.ASYNCPG_POOL_MAX_QUERIES,  # default is 50000
        )

        asyncpg_pools[loop_id] = pool

    return asyncpg_pools[loop_id]


async def close_asyncpg_pool():
    """
    Close the asyncpg connection pool for the current event loop

    Note: Only closes the pool for the current event loop.
    Other event loops' pools remain active.
    """
    current_loop = asyncio.get_running_loop()
    loop_id = id(current_loop)

    async with asyncpg_lock:
        if loop_id in asyncpg_pools:
            pool = asyncpg_pools[loop_id]
            await pool.close()
            del asyncpg_pools[loop_id]


async def close_all_asyncpg_pools():
    """
    Close all asyncpg connection pools across all event loops

    Warning: Only call this during application shutdown.
    Do not call from within an active event loop that has connections.
    """
    async with asyncpg_lock:
        for _, pool in list(asyncpg_pools.items()):
            try:
                await pool.close()
            except Exception:
                pass  # Ignore errors during shutdown
        asyncpg_pools.clear()
