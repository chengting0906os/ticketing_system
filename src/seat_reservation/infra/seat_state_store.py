"""
Seat State Repository
座位狀態資料訪問層
使用 Kvrocks Bitfield + Counter 優化存儲
"""

from typing import Dict, List, Optional, Tuple

from src.platform.logging.loguru_io import Logger
from src.platform.redis.redis_client import kvrocks_client


# 座位狀態編碼 (2 bits)
SEAT_STATUS_AVAILABLE = 0  # 0b00
SEAT_STATUS_RESERVED = 1  # 0b01
SEAT_STATUS_SOLD = 2  # 0b10
SEAT_STATUS_UNAVAILABLE = 3  # 0b11

STATUS_TO_BITFIELD = {
    'AVAILABLE': SEAT_STATUS_AVAILABLE,
    'RESERVED': SEAT_STATUS_RESERVED,
    'SOLD': SEAT_STATUS_SOLD,
    'UNAVAILABLE': SEAT_STATUS_UNAVAILABLE,
}

BITFIELD_TO_STATUS = {
    SEAT_STATUS_AVAILABLE: 'AVAILABLE',
    SEAT_STATUS_RESERVED: 'RESERVED',
    SEAT_STATUS_SOLD: 'SOLD',
    SEAT_STATUS_UNAVAILABLE: 'UNAVAILABLE',
}


class SeatStateStore:
    """
    座位狀態資料訪問層

    資料結構：
    1. Bitfield: seats_bf:{event_id}:{section}-{subsection}
       - 每個座位 2 bits (500 seats = 1000 bits = 125 bytes)
       - Index 計算: (row-1) * 20 + (seat_num-1)

    2. Row Counters: row_avail:{event_id}:{section}-{subsection}:{row}
       - String integer (0-20)

    3. Subsection Counter: subsection_avail:{event_id}:{section}-{subsection}
       - String integer (0-500)

    4. Seat Metadata: seat_meta:{event_id}:{section}-{subsection}:{row}
       - Hash {seat_num: price}

    5. Section Stats (legacy): section_stats:{event_id}:{section_id}
       - Hash (用於 API 查詢)
    """

    @staticmethod
    def _calculate_seat_index(row: int, seat_num: int) -> int:
        """計算座位在 Bitfield 中的 index"""
        return (row - 1) * 20 + (seat_num - 1)

    @staticmethod
    def _parse_seat_id(seat_id: str) -> Tuple[int, str, int, int, int]:
        """
        解析座位 ID
        Returns: (event_id, section, subsection, row, seat_num)
        """
        parts = seat_id.split('-')
        if len(parts) < 4:
            raise ValueError(f'Invalid seat_id format: {seat_id}')

        section, subsection, row, seat_num = parts[0], int(parts[1]), int(parts[2]), int(parts[3])
        return 0, section, subsection, row, seat_num  # event_id will be provided separately

    async def set_seat_status(
        self,
        event_id: int,
        section: str,
        subsection: int,
        row: int,
        seat_num: int,
        status: str,
        price: int,
    ) -> bool:
        """
        設置座位狀態（使用 Bitfield）

        Args:
            event_id: 活動 ID
            section: 區域 (e.g., "A")
            subsection: 子區域 (e.g., 1)
            row: 排 (1-25)
            seat_num: 座位號 (1-20)
            status: 狀態 ('AVAILABLE', 'RESERVED', 'SOLD', 'UNAVAILABLE')
            price: 價格

        Returns:
            是否成功
        """
        try:
            client = await kvrocks_client.connect()

            # 1. 計算 Bitfield index
            index = self._calculate_seat_index(row, seat_num)
            status_value = STATUS_TO_BITFIELD[status]

            # 2. 取得舊狀態（用於計數器更新）
            bf_key = f'seats_bf:{event_id}:{section}-{subsection}'
            old_status_values = await client.bitfield(
                bf_key, operations=[('GET', 'u2', f'#{index}')]
            )
            old_status_value = old_status_values[0] if old_status_values else None

            # 3. 更新 Bitfield
            await client.bitfield(bf_key, operations=[('SET', 'u2', f'#{index}', status_value)])

            # 4. 更新 Counter (只追蹤 AVAILABLE 狀態)
            row_counter_key = f'row_avail:{event_id}:{section}-{subsection}:{row}'
            subsection_counter_key = f'subsection_avail:{event_id}:{section}-{subsection}'

            if old_status_value is not None:
                old_status = BITFIELD_TO_STATUS.get(old_status_value)

                # AVAILABLE -> 其他狀態：遞減
                if old_status == 'AVAILABLE' and status != 'AVAILABLE':
                    await client.decr(row_counter_key)
                    await client.decr(subsection_counter_key)

                # 其他狀態 -> AVAILABLE：遞增
                elif old_status != 'AVAILABLE' and status == 'AVAILABLE':
                    await client.incr(row_counter_key)
                    await client.incr(subsection_counter_key)

                # AVAILABLE -> AVAILABLE 或 RESERVED -> SOLD：無計數器變化
            else:
                # 初始化 (從 make reset)
                if status == 'AVAILABLE':
                    await client.incr(row_counter_key)
                    await client.incr(subsection_counter_key)

            # 5. 存儲價格 Metadata
            meta_key = f'seat_meta:{event_id}:{section}-{subsection}:{row}'
            await client.hset(meta_key, seat_num, price)

            return True

        except Exception as e:
            Logger.base.error(f'❌ [REPO] Failed to set seat status: {e}')
            return False

    async def get_seat_status(
        self,
        event_id: int,
        section: str,
        subsection: int,
        row: int,
        seat_num: int,
    ) -> Optional[str]:
        """
        查詢座位狀態

        Returns:
            座位狀態 ('AVAILABLE', 'RESERVED', 'SOLD', 'UNAVAILABLE') 或 None
        """
        try:
            client = await kvrocks_client.connect()

            index = self._calculate_seat_index(row, seat_num)
            bf_key = f'seats_bf:{event_id}:{section}-{subsection}'

            results = await client.bitfield(bf_key, operations=[('GET', 'u2', f'#{index}')])

            if results and results[0] is not None:
                return BITFIELD_TO_STATUS.get(results[0])
            return None

        except Exception as e:
            Logger.base.error(f'❌ [REPO] Failed to get seat status: {e}')
            return None

    async def get_row_available_count(
        self,
        event_id: int,
        section: str,
        subsection: int,
        row: int,
    ) -> int:
        """
        查詢排可售數（O(1)）

        Returns:
            該排剩餘可售座位數 (0-20)
        """
        try:
            client = await kvrocks_client.connect()
            counter_key = f'row_avail:{event_id}:{section}-{subsection}:{row}'
            count = await client.get(counter_key)
            return int(count) if count else 0

        except Exception as e:
            Logger.base.error(f'❌ [REPO] Failed to get row available count: {e}')
            return 0

    async def get_subsection_available_count(
        self,
        event_id: int,
        section: str,
        subsection: int,
    ) -> int:
        """
        查詢 subsection 可售數（O(1)）

        Returns:
            該 subsection 剩餘可售座位數 (0-500)
        """
        try:
            client = await kvrocks_client.connect()
            counter_key = f'subsection_avail:{event_id}:{section}-{subsection}'
            count = await client.get(counter_key)
            return int(count) if count else 0

        except Exception as e:
            Logger.base.error(f'❌ [REPO] Failed to get subsection available count: {e}')
            return 0

    async def get_row_seats(
        self,
        event_id: int,
        section: str,
        subsection: int,
        row: int,
    ) -> List[Dict]:
        """
        查詢整排座位狀態（批量）

        Returns:
            座位列表 [{'seat_num': 1, 'status': 'AVAILABLE', 'price': 3000}, ...]
        """
        try:
            client = await kvrocks_client.connect()

            # 1. 批量讀取該排的 20 個座位狀態（20 seats × 2 bits = 40 bits）
            bf_key = f'seats_bf:{event_id}:{section}-{subsection}'
            start_index = self._calculate_seat_index(row, 1)

            operations = [('GET', 'u2', f'#{start_index + i}') for i in range(20)]
            status_values = await client.bitfield(bf_key, operations=operations)

            # 2. 讀取價格
            meta_key = f'seat_meta:{event_id}:{section}-{subsection}:{row}'
            prices = await client.hgetall(meta_key)

            # 3. 組合結果
            seats = []
            for i, status_value in enumerate(status_values):
                seat_num = i + 1
                if status_value is not None:
                    seats.append(
                        {
                            'seat_num': seat_num,
                            'status': BITFIELD_TO_STATUS.get(status_value, 'UNAVAILABLE'),
                            'price': int(prices.get(str(seat_num), 0)),
                        }
                    )

            return seats

        except Exception as e:
            Logger.base.error(f'❌ [REPO] Failed to get row seats: {e}')
            return []

    def set_seat_status_sync(
        self,
        event_id: int,
        section: str,
        subsection: int,
        row: int,
        seat_num: int,
        status: str,
        price: int,
    ) -> bool:
        """
        設置座位狀態（同步版本，用於 Kafka Consumer）

        Args:
            event_id: 活動 ID
            section: 區域 (e.g., "A")
            subsection: 子區域 (e.g., 1)
            row: 排 (1-25)
            seat_num: 座位號 (1-20)
            status: 狀態 ('AVAILABLE', 'RESERVED', 'SOLD', 'UNAVAILABLE')
            price: 價格

        Returns:
            是否成功
        """
        try:
            from src.platform.redis.redis_client import kvrocks_client_sync

            client = kvrocks_client_sync.connect()

            # 1. 計算 Bitfield index
            index = self._calculate_seat_index(row, seat_num)
            status_value = STATUS_TO_BITFIELD[status]

            # 2. 檢查這個具體座位是否已經初始化過
            # 使用 seat_meta Hash 來判斷座位是否已存在
            bf_key = f'seats_bf:{event_id}:{section}-{subsection}'
            bit_offset = index * 2
            meta_key = f'seat_meta:{event_id}:{section}-{subsection}:{row}'

            # 如果該座位的價格已存在於 Hash 中，表示已初始化過
            is_new_seat = not client.hexists(meta_key, seat_num)

            # 3. 取得舊狀態（用於計數器更新）
            if not is_new_seat:
                old_status_values = client.bitfield(bf_key).get('u2', bit_offset).execute()
                old_status_value = old_status_values[0] if old_status_values else None
            else:
                old_status_value = None

            # 4. 更新 Bitfield
            client.bitfield(bf_key).set('u2', bit_offset, status_value).execute()

            # 5. 更新 Counter (只追蹤 AVAILABLE 狀態)
            row_counter_key = f'row_avail:{event_id}:{section}-{subsection}:{row}'
            subsection_counter_key = f'subsection_avail:{event_id}:{section}-{subsection}'

            if old_status_value is not None:
                # 更新現有座位
                old_status = BITFIELD_TO_STATUS.get(old_status_value)

                # AVAILABLE -> 其他狀態：遞減
                if old_status == 'AVAILABLE' and status != 'AVAILABLE':
                    client.decr(row_counter_key)
                    client.decr(subsection_counter_key)

                # 其他狀態 -> AVAILABLE：遞增
                elif old_status != 'AVAILABLE' and status == 'AVAILABLE':
                    client.incr(row_counter_key)
                    client.incr(subsection_counter_key)

                # AVAILABLE -> AVAILABLE 或 RESERVED -> SOLD：無計數器變化
            else:
                # 初始化新座位
                if status == 'AVAILABLE':
                    client.incr(row_counter_key)
                    client.incr(subsection_counter_key)

            # 5. 存儲價格 Metadata
            meta_key = f'seat_meta:{event_id}:{section}-{subsection}:{row}'
            client.hset(meta_key, seat_num, price)

            return True

        except Exception as e:
            Logger.base.error(f'❌ [REPO-SYNC] Failed to set seat status: {e}')
            return False


# 全域單例
seat_state_store = SeatStateStore()
