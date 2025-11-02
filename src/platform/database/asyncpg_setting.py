import asyncio

import asyncpg
from uuid_utils import UUID

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger


# Global connection pools per event loop
asyncpg_pools: dict[int, asyncpg.Pool] = {}


async def get_asyncpg_pool() -> asyncpg.Pool:
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

    async def init_connection(conn):
        """Initialize each connection with UUID codec"""

        def _uuid_decoder(value: bytes) -> UUID:
            """Decode PostgreSQL UUID binary data to uuid_utils.UUID"""
            return UUID(bytes=value)

        def _uuid_encoder(value: UUID) -> bytes:
            """Encode uuid_utils.UUID to binary for PostgreSQL"""
            return value.bytes

        await conn.set_type_codec(
            'uuid',
            encoder=_uuid_encoder,
            decoder=_uuid_decoder,
            schema='pg_catalog',
            format='binary',
        )

    pool = await asyncpg.create_pool(
        dsn,
        min_size=settings.ASYNCPG_POOL_MIN_SIZE,
        max_size=settings.ASYNCPG_POOL_MAX_SIZE,
        command_timeout=settings.ASYNCPG_POOL_COMMAND_TIMEOUT,
        max_inactive_connection_lifetime=settings.ASYNCPG_POOL_MAX_INACTIVE_LIFETIME,
        timeout=settings.ASYNCPG_POOL_TIMEOUT,
        max_queries=settings.ASYNCPG_POOL_MAX_QUERIES,  # default is 50000
        loop=current_loop,  # Explicitly bind pool to this event loop
        init=init_connection,  # Initialize each connection with UUID codec
    )

    asyncpg_pools[loop_id] = pool

    return asyncpg_pools[loop_id]


async def warmup_asyncpg_pool() -> int:
    """
    Strategy:
    1. Acquire MIN_SIZE connections from pool (blocking)
    2. Release them all back to pool
    3. All connections now in warm pool ready for immediate use

    """
    pool = await get_asyncpg_pool()
    connections = []

    try:
        Logger.base.info(
            f'🔥 [Pool Warmup] Starting warmup (target={settings.ASYNCPG_POOL_MIN_SIZE})...'
        )

        # Acquire connections up to MIN_SIZE only (avoid overwhelming Aurora)
        for i in range(settings.ASYNCPG_POOL_MIN_SIZE):
            try:
                conn = await pool.acquire(timeout=5.0)
                connections.append(conn)

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
