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
    """
    Multi-Event-Loop Safe Kvrocks Client

    Maintains separate connection pools per event loop to support
    concurrent services (e.g., FastAPI + MQ Consumer) without reconnection overhead.

    Architecture:
    - FastAPI service: runs in main event loop
    - MQ Consumer: runs in separate event loop via start_blocking_portal()
    - Each loop gets its own connection pool for isolation

    Usage:
        # In startup (lifespan):
        await kvrocks_client.initialize()

        # In request handlers/use cases:
        client = kvrocks_client.get_client()
        await client.get("key")
    """

    def __init__(self):
        self._clients: dict[int, Redis] = {}
        self._lock = asyncio.Lock()

    async def initialize(self) -> Redis:
        """
        Initialize connection pool for current event loop (call during startup).

        Creates connection pool and verifies connectivity.
        Subsequent calls return existing pool (idempotent).
        """
        loop_id = id(asyncio.get_running_loop())

        if loop_id in self._clients:
            Logger.base.info(f'📡 [KVROCKS] Pool already exists for loop {loop_id}')
            return self._clients[loop_id]

        async with self._lock:
            if loop_id in self._clients:
                return self._clients[loop_id]

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
            self._clients[loop_id] = Redis.from_pool(pool)
            Logger.base.info(f'📡 [KVROCKS] Connection pool created for loop {loop_id}')

            # Verify connection with a ping (fail-fast)
            try:
                await self._clients[loop_id].ping()
                Logger.base.info(f'✅ [KVROCKS] Connection verified for loop {loop_id}')
            except Exception as e:
                # Clean up failed connection
                await self._clients[loop_id].aclose()
                del self._clients[loop_id]
                Logger.base.error(f'❌ [KVROCKS] Connection failed for loop {loop_id}: {e}')
                raise

        return self._clients[loop_id]

    def get_client(self) -> Redis:
        """
        Get Redis client from pool (non-async, fast).

        Must call initialize() first during startup, otherwise raises RuntimeError.
        Use this method in request handlers and use cases.
        """
        loop_id = id(asyncio.get_running_loop())

        if loop_id not in self._clients:
            raise RuntimeError(
                f'Kvrocks client not initialized for loop {loop_id}. '
                'Call await kvrocks_client.initialize() during startup.'
            )

        return self._clients[loop_id]

    async def connect(self) -> Redis:
        """
        Legacy method for backward compatibility.
        Prefer initialize() in startup and get_client() in handlers.
        """
        return await self.initialize()

    async def disconnect(self):
        """Close connection for current event loop"""
        loop_id = id(asyncio.get_running_loop())
        async with self._lock:
            if client := self._clients.pop(loop_id, None):
                await client.aclose()
                Logger.base.info(f'📡 [KVROCKS] Connection closed for loop {loop_id}')

    async def disconnect_all(self):
        """Close all connections (shutdown only)"""
        async with self._lock:
            for loop_id, client in list(self._clients.items()):
                try:
                    await client.aclose()
                    Logger.base.info(f'📡 [KVROCKS] Connection closed for loop {loop_id}')
                except Exception as e:
                    Logger.base.warning(f'⚠️ [KVROCKS] Error closing {loop_id}: {e}')
            self._clients.clear()


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
