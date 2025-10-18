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
from src.platform.logging.loguru_io import Logger


# Global connection pools per event loop
asyncpg_pools: dict[int, asyncpg.Pool] = {}


async def get_asyncpg_pool() -> asyncpg.Pool:
    """
    Get or create asyncpg connection pool for the current event loop

    Connection lifecycle management:
    - max_inactive_connection_lifetime: Recycle idle connections after 5 min
    - max_queries: Recycle connections after 50k queries to prevent memory leaks
    - timeout: Fail fast if pool is exhausted (10s)

    Each event loop gets its own pool to prevent connection errors when
    multiple services (FastAPI + MQ Consumer) run concurrently.

    Note: Pool is created eagerly at application startup to avoid race conditions.
    This function should only be called during startup or if pool already exists.

    Returns:
        asyncpg.Pool: Connection pool for high-performance operations
    """
    current_loop = asyncio.get_running_loop()
    loop_id = id(current_loop)

    # Fast path: pool already exists for this loop (99.9% of calls)
    if loop_id in asyncpg_pools:
        pool = asyncpg_pools[loop_id]
        # Log pool stats for debugging

        Logger.base.debug(
            f'📊 [Pool Stats] size={pool.get_size()}, free={pool.get_idle_size()}, '
            f'max={pool.get_max_size()}, min={pool.get_min_size()}'
        )
        return pool

    # Slow path: create new pool (should only happen at startup)
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
        loop=current_loop,  # Explicitly bind pool to this event loop
    )

    asyncpg_pools[loop_id] = pool

    return asyncpg_pools[loop_id]


async def warmup_asyncpg_pool() -> int:
    """
    Warmup asyncpg pool by pre-creating connections up to MAX_SIZE

    This eliminates "connect" spans during request handling by forcing
    the pool to expand to its full capacity at startup time.

    Strategy:
    1. Acquire all MAX_SIZE connections from pool (blocking)
    2. Release them all back to pool
    3. All connections now in warm pool ready for immediate use

    Returns:
        Number of connections warmed up
    """
    pool = await get_asyncpg_pool()
    connections = []

    try:
        Logger.base.info(
            f'🔥 [Pool Warmup] Starting warmup (target={settings.ASYNCPG_POOL_MAX_SIZE})...'
        )

        # Acquire connections up to MAX_SIZE
        for i in range(settings.ASYNCPG_POOL_MAX_SIZE):
            try:
                conn = await pool.acquire(timeout=5.0)
                connections.append(conn)
                Logger.base.debug(
                    f'   ✓ Created connection {i + 1}/{settings.ASYNCPG_POOL_MAX_SIZE}'
                )
            except asyncio.TimeoutError:
                Logger.base.warning(f'   ⚠️  Pool warmup timeout at {i + 1} connections')
                break
            except Exception as e:
                Logger.base.error(f'   ❌ Pool warmup error: {e}')
                break

        # Release all connections back to pool
        for conn in connections:
            await pool.release(conn)

        Logger.base.info(
            f'✅ [Pool Warmup] Completed: {len(connections)} connections ready '
            f'(size={pool.get_size()}, idle={pool.get_idle_size()})'
        )

        return len(connections)

    except Exception as e:
        Logger.base.error(f'❌ [Pool Warmup] Failed: {e}')
        # Release any acquired connections on error
        for conn in connections:
            try:
                await pool.release(conn)
            except Exception:
                pass
        raise


async def close_asyncpg_pool():
    """
    Close the asyncpg connection pool for the current event loop

    Note: Only closes the pool for the current event loop.
    Other event loops' pools remain active.
    """
    current_loop = asyncio.get_running_loop()
    loop_id = id(current_loop)

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
    for _, pool in list(asyncpg_pools.items()):
        try:
            await pool.close()
        except Exception:
            pass  # Ignore errors during shutdown
    asyncpg_pools.clear()
