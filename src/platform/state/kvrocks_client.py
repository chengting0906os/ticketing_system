"""
Kvrocks Client - Pure Redis Protocol Client with Connection Pooling
純粹的 Redis 客戶端，不包含業務邏輯
Kvrocks = Redis 協議 + Kvrocks 存儲引擎（持久化、零丟失）

Connection Pooling:
- Async client uses explicit ConnectionPool with configurable max_connections
- Sync client uses internal ConnectionPool (created automatically by redis.from_url)
- Health checks and timeouts configured via settings
"""

import asyncio
from typing import Optional

from redis import Redis as SyncRedis
from redis.asyncio import ConnectionPool as AsyncConnectionPool
from redis.asyncio import Redis

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger


class KvrocksClient:
    def __init__(self):
        self._client: Optional[Redis] = None
        self._pool: Optional[AsyncConnectionPool] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _create_pool(self) -> AsyncConnectionPool:
        """Create connection pool with configured settings"""
        return AsyncConnectionPool.from_url(
            f'redis://{settings.KVROCKS_HOST}:{settings.KVROCKS_PORT}/{settings.KVROCKS_DB}',
            password=settings.KVROCKS_PASSWORD if settings.KVROCKS_PASSWORD else None,
            decode_responses=settings.REDIS_DECODE_RESPONSES,
            max_connections=settings.KVROCKS_POOL_MAX_CONNECTIONS,
            socket_timeout=settings.KVROCKS_POOL_SOCKET_TIMEOUT,
            socket_connect_timeout=settings.KVROCKS_POOL_SOCKET_CONNECT_TIMEOUT,
            socket_keepalive=settings.KVROCKS_POOL_SOCKET_KEEPALIVE,
            health_check_interval=settings.KVROCKS_POOL_HEALTH_CHECK_INTERVAL,
        )

    async def connect(self) -> Redis:
        current_loop = asyncio.get_running_loop()

        # If client exists but is bound to a different event loop, close it first
        if self._client is not None and self._loop is not current_loop:
            Logger.base.warning('🔄 [KVROCKS] Event loop changed, reconnecting...')
            try:
                await self._client.aclose()
                if self._pool:
                    await self._pool.aclose()
            except Exception as e:
                Logger.base.warning(f'⚠️ [KVROCKS] Error closing old connection: {e}')
            self._client = None
            self._pool = None
            self._loop = None

        if self._client is None:
            self._pool = self._create_pool()
            self._client = Redis.from_pool(self._pool)
            self._loop = current_loop
            Logger.base.info(
                f'📡 [KVROCKS] Connected with pool (max_connections={settings.KVROCKS_POOL_MAX_CONNECTIONS})'
            )
        return self._client

    async def disconnect(self):
        """關閉 Kvrocks 連線與連線池"""
        if self._client:
            # CRITICAL: aclose() properly cleans: (1) connection pool + pending tasks
            # (2) event loop bindings (prevents "Event loop is closed" in tests)
            # (3) sockets/file descriptors. close() is deprecated & leaves dangling refs
            await self._client.aclose()
            self._client = None
            Logger.base.info('🔌 [KVROCKS] Client disconnected')

        if self._pool:
            await self._pool.aclose()
            self._pool = None
            Logger.base.info('🔌 [KVROCKS] Pool closed')

        self._loop = None


# 全域單例
kvrocks_client = KvrocksClient()


class KvrocksClientSync:
    """
    同步版本的 Kvrocks 客戶端
    用於 Kafka Consumer 等同步環境

    Note: redis.from_url() automatically creates an internal ConnectionPool,
    so explicit pool management is not needed for the sync client.
    """

    def __init__(self):
        self._client: Optional[SyncRedis] = None

    def connect(self) -> SyncRedis:
        """建立 Kvrocks 連線（同步）"""
        if self._client is None:
            # from_url() creates internal ConnectionPool automatically with pool settings
            self._client = SyncRedis.from_url(
                f'redis://{settings.KVROCKS_HOST}:{settings.KVROCKS_PORT}/{settings.KVROCKS_DB}',
                password=settings.KVROCKS_PASSWORD if settings.KVROCKS_PASSWORD else None,
                decode_responses=settings.REDIS_DECODE_RESPONSES,
                max_connections=settings.KVROCKS_POOL_MAX_CONNECTIONS,
                socket_timeout=settings.KVROCKS_POOL_SOCKET_TIMEOUT,
                socket_connect_timeout=settings.KVROCKS_POOL_SOCKET_CONNECT_TIMEOUT,
                socket_keepalive=settings.KVROCKS_POOL_SOCKET_KEEPALIVE,
                health_check_interval=settings.KVROCKS_POOL_HEALTH_CHECK_INTERVAL,
            )
            Logger.base.info(
                f'📡 [KVROCKS-SYNC] Connected (pool max_connections={settings.KVROCKS_POOL_MAX_CONNECTIONS})'
            )
        return self._client

    def disconnect(self):
        """關閉 Kvrocks 連線"""
        if self._client:
            self._client.close()
            self._client = None
            Logger.base.info('🔌 [KVROCKS-SYNC] Disconnected')

    @property
    def client(self) -> SyncRedis:
        """取得 Redis 客戶端（同步方式）"""
        if self._client is None:
            raise RuntimeError('Kvrocks client not connected. Call connect() first.')
        return self._client


# 全域單例 - 同步版本
kvrocks_client_sync = KvrocksClientSync()
