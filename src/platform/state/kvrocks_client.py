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

    @Logger.io
    async def list_all_subsection_status(self, *, event_id: int):
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
            Logger.base.error(f'❌ [KVROCKS-STATS] Failed to get all sections: {e}')
            return {}

    @Logger.io
    async def list_subsection_seats_detail(
        self, *, event_id: int, section: str, subsection: int, max_rows: int, seats_per_row: int
    ):
        """
        獲取某個 section 所有座位的詳細狀態

        Args:
            event_id: 活動 ID
            section: 區域 (e.g., "A")
            subsection: 子區域 (e.g., 1)
            max_rows: 排數
            seats_per_row: 每排座位數

        Returns:
            List of seat details: [{"seat_id": "A-1-1-1", "status": "available", "price": 3000}, ...]
        """
        try:
            client = await kvrocks_client.connect()

            # Status mapping: Bitfield value -> status string
            BITFIELD_TO_STATUS = {0: 'available', 1: 'reserved', 2: 'sold', 3: 'unavailable'}

            section_id = f'{section}-{subsection}'
            bf_key = f'seats_bf:{event_id}:{section_id}'

            # 檢查 bitfield 是否已初始化
            exists = await client.exists(bf_key)
            if not exists:
                Logger.base.warning(f'⚠️ [KVROCKS] Bitfield not initialized: {bf_key}')
                return []

            # 計算總座位數
            total_seats = max_rows * seats_per_row

            # 使用 GETRANGE 快速讀取所有座位狀態 (2 bits per seat)
            nbytes = (2 * total_seats + 7) // 8  # 計算需要的位元組數
            raw_data = await client.getrange(bf_key, 0, nbytes - 1)  # 讀取原始資料

            # 將字串轉為位元組 (因為 decode_responses=True)
            if raw_data is None or raw_data == '':
                # Bitfield 存在但為空 (所有座位預設為 available)
                raw_bytes = b''
            elif isinstance(raw_data, str):
                raw_bytes = raw_data.encode('latin-1')
            else:
                raw_bytes = raw_data

            # 如果讀取的資料不足，補0 (未初始化的座位狀態為0=available)
            if len(raw_bytes) < nbytes:
                raw_bytes += b'\x00' * (nbytes - len(raw_bytes))

            # 解析位元組為座位狀態 (每個 byte = 4 個座位，高位在前)
            bitfield_values = []
            for byte_val in raw_bytes:
                bitfield_values.extend(
                    [
                        (byte_val >> 6) & 0b11,  # 第1個座位 (最高2位)
                        (byte_val >> 4) & 0b11,  # 第2個座位
                        (byte_val >> 2) & 0b11,  # 第3個座位
                        byte_val & 0b11,  # 第4個座位 (最低2位)
                    ]
                )
                if len(bitfield_values) >= total_seats:
                    break
            bitfield_values = bitfield_values[:total_seats]  # 截取到實際座位數

            # 獲取價格信息 (從 seat_meta Hash 讀取)
            # seat_meta:{event_id}:{section}-{subsection}:{row} -> {seat_num: price}
            price_cache = {}
            pipe = client.pipeline()
            for row in range(1, max_rows + 1):
                meta_key = f'seat_meta:{event_id}:{section_id}:{row}'
                pipe.hgetall(meta_key)

            price_results = await pipe.execute()
            for row, row_prices in enumerate(price_results, start=1):
                price_cache[row] = row_prices if row_prices else {}

            # 組合結果
            seats = []
            for i, status_value in enumerate(bitfield_values):
                row = (i // seats_per_row) + 1
                seat_num = (i % seats_per_row) + 1
                seat_id = f'{section}-{subsection}-{row}-{seat_num}'

                # 獲取價格 (從 cache 中取得)
                row_prices = price_cache.get(row, {})
                price = int(row_prices.get(str(seat_num), 0)) if row_prices else 0

                seats.append(
                    {
                        'seat_id': seat_id,
                        'status': BITFIELD_TO_STATUS.get(status_value, 'unknown'),
                        'price': price,
                        'row': row,
                        'seat_num': seat_num,
                    }
                )

            Logger.base.info(f'📋 [KVROCKS] Retrieved {len(seats)} seats for section {section_id}')

            return seats

        except Exception as e:
            Logger.base.error(f'❌ [KVROCKS] Failed to get seats detail: {e}')
            return []


# Legacy stats client for API compatibility
kvrocks_stats_client = KvrocksStatsClient()
