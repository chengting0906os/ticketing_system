"""
Kvrocks Client - Pure Redis Protocol Client
純粹的 Redis 客戶端，不包含業務邏輯
Kvrocks = Redis 協議 + Kvrocks 存儲引擎（持久化、零丟失）
"""

from typing import Optional

import redis
from redis import Redis as SyncRedis
import redis.asyncio as aioredis
from redis.asyncio import Redis

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger


class KvrocksClient:
    def __init__(self):
        self._client: Optional[Redis] = None

    async def connect(self) -> Redis:
        if self._client is None:
            self._client = await aioredis.from_url(
                f'redis://{settings.KVROCKS_HOST}:{settings.KVROCKS_PORT}/{settings.KVROCKS_DB}',
                password=settings.KVROCKS_PASSWORD if settings.KVROCKS_PASSWORD else None,
                decode_responses=settings.REDIS_DECODE_RESPONSES,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )
            Logger.base.info('📡 [KVROCKS] Connected')
        return self._client

    async def disconnect(self):
        """關閉 Kvrocks 連線"""
        if self._client:
            # CRITICAL: aclose() properly cleans: (1) connection pool + pending tasks
            # (2) event loop bindings (prevents "Event loop is closed" in tests)
            # (3) sockets/file descriptors. close() is deprecated & leaves dangling refs
            await self._client.aclose()
            self._client = None
            Logger.base.info('🔌 [KVROCKS] Disconnected')


# 全域單例
kvrocks_client = KvrocksClient()


class KvrocksClientSync:
    """
    同步版本的 Kvrocks 客戶端
    用於 Kafka Consumer 等同步環境
    """

    def __init__(self):
        self._client: Optional[SyncRedis] = None

    def connect(self) -> SyncRedis:
        """建立 Kvrocks 連線（同步）"""
        if self._client is None:
            self._client = redis.from_url(
                f'redis://{settings.KVROCKS_HOST}:{settings.KVROCKS_PORT}/{settings.KVROCKS_DB}',
                password=settings.KVROCKS_PASSWORD if settings.KVROCKS_PASSWORD else None,
                decode_responses=settings.REDIS_DECODE_RESPONSES,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )
            Logger.base.info('📡 [KVROCKS-SYNC] Connected')
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
