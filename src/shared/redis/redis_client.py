"""
Kvrocks Client - Pure Redis Protocol Client
純粹的 Redis 客戶端，不包含業務邏輯
Kvrocks = Redis 協議 + Kvrocks 存儲引擎（持久化、零丟失）
"""

from typing import Optional

import redis
import redis.asyncio as aioredis
from redis import Redis as SyncRedis
from redis.asyncio import Redis

from src.shared.config.core_setting import settings
from src.shared.logging.loguru_io import Logger


class KvrocksClient:
    """
    純粹的 Kvrocks 客戶端
    只負責 Redis 連線管理，不包含任何業務邏輯
    """

    def __init__(self):
        self._client: Optional[Redis] = None

    async def connect(self) -> Redis:
        """建立 Kvrocks 連線"""
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
            await self._client.close()
            self._client = None
            Logger.base.info('🔌 [KVROCKS] Disconnected')

    @property
    def client(self) -> Redis:
        """取得 Redis 客戶端（同步方式）"""
        if self._client is None:
            raise RuntimeError('Kvrocks client not connected. Call connect() first.')
        return self._client


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


class KvrocksStatsClient:
    """
    Legacy Stats Client for API compatibility
    讀取 section_stats Hash (由 consumer 維護)
    """

    async def get_section_stats(self, *, event_id: int, section_id: str):
        """查詢單個 section 統計"""
        try:
            client = await kvrocks_client.connect()
            stats_key = f'section_stats:{event_id}:{section_id}'
            stats = await client.hgetall(stats_key)

            if not stats:
                return None

            return {
                'section_id': stats.get('section_id'),
                'event_id': int(stats.get('event_id', 0)),
                'available': int(stats.get('available', 0)),
                'reserved': int(stats.get('reserved', 0)),
                'sold': int(stats.get('sold', 0)),
                'total': int(stats.get('total', 0)),
                'updated_at': int(stats.get('updated_at', 0)),
            }

        except Exception as e:
            from src.shared.logging.loguru_io import Logger

            Logger.base.error(f'❌ [KVROCKS-STATS] Failed to get section {section_id}: {e}')
            return None

    async def get_all_section_stats(self, *, event_id: int):
        """查詢活動的所有 section 統計"""
        try:
            client = await kvrocks_client.connect()

            # 1. 從索引取得所有 section_id
            index_key = f'event_sections:{event_id}'
            section_ids = await client.zrange(index_key, 0, -1)

            if not section_ids:
                return {}

            # 2. 使用 Pipeline 批量查詢
            pipe = client.pipeline()
            for section_id in section_ids:
                stats_key = f'section_stats:{event_id}:{section_id}'
                pipe.hgetall(stats_key)

            results = await pipe.execute()

            # 3. 組合結果
            all_stats = {}
            for section_id, stats in zip(section_ids, results, strict=False):
                if stats:
                    all_stats[section_id] = {
                        'section_id': stats.get('section_id'),
                        'event_id': int(stats.get('event_id', 0)),
                        'available': int(stats.get('available', 0)),
                        'reserved': int(stats.get('reserved', 0)),
                        'sold': int(stats.get('sold', 0)),
                        'total': int(stats.get('total', 0)),
                        'updated_at': int(stats.get('updated_at', 0)),
                    }

            return all_stats

        except Exception as e:
            from src.shared.logging.loguru_io import Logger

            Logger.base.error(f'❌ [KVROCKS-STATS] Failed to get all sections: {e}')
            return {}


# Legacy stats client for API compatibility
kvrocks_stats_client = KvrocksStatsClient()
