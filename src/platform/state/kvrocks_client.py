from typing import Optional

from redis.asyncio import ConnectionPool as AsyncConnectionPool, Redis as AsyncRedis

from src.platform.config.core_setting import settings


class KvrocksClient:
    """
    Async Kvrocks Client with connection pool.

    Single connection pool per process.

    Usage:
        await kvrocks_client.initialize()  # In startup
        client = kvrocks_client.get_client()  # In handlers
    """

    def __init__(self) -> None:
        self._client: Optional[AsyncRedis] = None

    async def initialize(self) -> AsyncRedis:
        """Initialize connection pool (idempotent)"""
        if self._client is not None:
            return self._client

        pool = AsyncConnectionPool.from_url(
            f'redis://{settings.KVROCKS_HOST}:{settings.KVROCKS_PORT}/{settings.KVROCKS_DB}',
            password=settings.KVROCKS_PASSWORD if settings.KVROCKS_PASSWORD else None,
            decode_responses=settings.REDIS_DECODE_RESPONSES,
            max_connections=settings.KVROCKS_POOL_MAX_CONNECTIONS,
            socket_timeout=settings.KVROCKS_POOL_SOCKET_TIMEOUT,
            socket_connect_timeout=settings.KVROCKS_POOL_SOCKET_CONNECT_TIMEOUT,
            socket_keepalive=settings.KVROCKS_POOL_SOCKET_KEEPALIVE,
            health_check_interval=settings.KVROCKS_POOL_HEALTH_CHECK_INTERVAL,
        )
        self._client = AsyncRedis.from_pool(pool)
        await self._client.ping()  # Fail-fast

        return self._client

    def get_client(self) -> AsyncRedis:
        """Get Redis client"""
        if self._client is None:
            raise RuntimeError(
                'Kvrocks client not initialized. '
                'Call await kvrocks_client.initialize() during startup.'
            )
        return self._client

    async def connect(self) -> AsyncRedis:
        """Legacy compatibility"""
        return await self.initialize()

    async def disconnect(self):
        """Close connection pool"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# Global singleton
kvrocks_client = KvrocksClient()
