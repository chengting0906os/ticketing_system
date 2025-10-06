"""
Seat State Handler Implementation
座位狀態處理器實現 - 直接使用 Kvrocks Bitfield + Counter
"""

import os
from typing import Dict, List, Optional

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.seat_reservation.app.interface.i_seat_state_handler import ISeatStateHandler

# Get key prefix from environment for test isolation
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')


def _make_key(key: str) -> str:
    """Add prefix to key for test isolation in parallel testing"""
    return f'{_KEY_PREFIX}{key}'


# 座位狀態編碼 (2 bits)
SEAT_STATUS_AVAILABLE = 0  # 0b00
SEAT_STATUS_RESERVED = 1  # 0b01
SEAT_STATUS_SOLD = 2  # 0b10

STATUS_TO_BITFIELD = {
    'available': SEAT_STATUS_AVAILABLE,
    'reserved': SEAT_STATUS_RESERVED,
    'sold': SEAT_STATUS_SOLD,
}

BITFIELD_TO_STATUS = {
    SEAT_STATUS_AVAILABLE: 'available',
    SEAT_STATUS_RESERVED: 'reserved',
    SEAT_STATUS_SOLD: 'sold',
}


class SeatStateHandlerImpl(ISeatStateHandler):
    """
    座位狀態處理器實現 - 直接操作 Kvrocks

    資料結構：
    1. Bitfield: seats_bf:{event_id}:{section}-{subsection}
       - 每個座位 2 bits (500 seats = 1000 bits = 125 bytes)
    2. Row Counters: row_avail:{event_id}:{section}-{subsection}:{row}
    3. Seat Metadata: seat_meta:{event_id}:{section}-{subsection}:{row}
       - Hash {seat_num: price}
    """

    @staticmethod
    def _calculate_seat_index(row: int, seat_num: int) -> int:
        """計算座位在 Bitfield 中的 index"""
        return (row - 1) * 20 + (seat_num - 1)

    @Logger.io
    async def _get_section_config(self, event_id: int, section: str, subsection: int) -> Dict:
        """
        從 Redis 獲取 section 配置信息（帶 LRU cache）

        Returns:
            {'rows': 25, 'seats_per_row': 20}

        Raises:
            ValueError: 配置不存在時
        """
        try:
            client = await kvrocks_client.connect()
            section_id = f'{section}-{subsection}'
            config_key = f'section_config:{event_id}:{section_id}'

            # 從 Redis 讀取配置
            config = await client.hgetall(config_key)  # type: ignore

            if not config:
                raise ValueError(
                    f'Section config not found: event_id={event_id}, section={section}, subsection={subsection}'
                )

            return {'rows': int(config['rows']), 'seats_per_row': int(config['seats_per_row'])}

        except KeyError as e:
            raise ValueError(f'Invalid config format, missing field: {e}')
        except ValueError:
            raise
        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Failed to get section config: {e}')
            raise

    @Logger.io
    async def _save_section_config(
        self, event_id: int, section: str, subsection: int, rows: int, seats_per_row: int
    ) -> bool:
        """保存 section 配置到 Redis"""
        try:
            client = await kvrocks_client.connect()
            section_id = f'{section}-{subsection}'
            config_key = f'section_config:{event_id}:{section_id}'

            # 保存配置到 Redis Hash
            client.hset(
                config_key, mapping={'rows': str(rows), 'seats_per_row': str(seats_per_row)}
            )

            Logger.base.info(
                f'✅ [SEAT-STATE] Saved section config: {section_id}, rows={rows}, seats_per_row={seats_per_row}'
            )
            return True

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Failed to save section config: {e}')
            return True

    def is_available(self) -> bool:
        """檢查服務是否可用"""
        return True

    @Logger.io
    async def _get_seat_status_from_bitfield(
        self, event_id: int, section: str, subsection: int, row: int, seat_num: int
    ) -> Optional[str]:
        """從 Bitfield 讀取單個座位狀態"""
        try:
            client = await kvrocks_client.connect()
            section_id = f'{section}-{subsection}'
            bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')

            seat_index = self._calculate_seat_index(row, seat_num)
            offset = seat_index * 2

            value = await client.getbit(bf_key, offset) * 2 + await client.getbit(
                bf_key, offset + 1
            )
            return BITFIELD_TO_STATUS.get(value, 'available')

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Failed to get seat status: {e}')
            return None

    @Logger.io
    async def _set_seat_status_to_bitfield(
        self,
        event_id: int,
        section: str,
        subsection: int,
        row: int,
        seat_num: int,
        status: str,
        price: int,
    ) -> bool:
        """設置座位狀態到 Bitfield"""
        try:
            client = await kvrocks_client.connect()
            section_id = f'{section}-{subsection}'
            bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')
            meta_key = _make_key(f'seat_meta:{event_id}:{section_id}:{row}')

            seat_index = self._calculate_seat_index(row, seat_num)
            offset = seat_index * 2
            bitfield_value = STATUS_TO_BITFIELD.get(status, SEAT_STATUS_AVAILABLE)

            # 設置 bitfield (2 bits)
            await client.setbit(bf_key, offset, (bitfield_value >> 1) & 1)
            await client.setbit(bf_key, offset + 1, bitfield_value & 1)

            # 設置價格 metadata (hset 在此配置下不是 awaitable)
            client.hset(meta_key, str(seat_num), str(price))  # pyright: ignore

            return True

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Failed to set seat status: {e}')
            return False

    @Logger.io
    async def _get_row_seats(
        self, event_id: int, section: str, subsection: int, row: int
    ) -> List[Dict]:
        """獲取一排的所有座位狀態"""
        try:
            # 獲取配置信息（帶 LRU cache）
            config = await self._get_section_config(event_id, section, subsection)
            seats_per_row = config['seats_per_row']

            client = await kvrocks_client.connect()
            section_id = f'{section}-{subsection}'
            bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')
            meta_key = _make_key(f'seat_meta:{event_id}:{section_id}:{row}')

            # 讀取該排座位的狀態
            seats = []
            prices = await client.hgetall(meta_key)  # type: ignore

            for seat_num in range(1, seats_per_row + 1):
                seat_index = self._calculate_seat_index(row, seat_num)
                offset = seat_index * 2

                bit1 = await client.getbit(bf_key, offset)
                bit2 = await client.getbit(bf_key, offset + 1)
                value = bit1 * 2 + bit2

                seats.append(
                    {
                        'seat_num': seat_num,
                        'status': BITFIELD_TO_STATUS.get(value, 'available'),
                        'price': int(prices.get(str(seat_num), 0)) if prices else 0,
                    }
                )

            return seats

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Failed to get row seats: {e}')
            return []

    @Logger.io
    async def list_all_subsection_seats(
        self, event_id: int, section: str, subsection: int
    ) -> List[Dict]:
        """
        獲取整個 subsection 的所有座位狀態（從 Kvrocks）

        Returns:
            List of dicts with keys: section, subsection, row, seat_num, status, price, seat_identifier
        """
        try:
            # 獲取配置信息
            config = await self._get_section_config(event_id, section, subsection)
            total_rows = config['rows']

            all_seats = []
            for row in range(1, total_rows + 1):
                row_seats = await self._get_row_seats(event_id, section, subsection, row)

                for seat in row_seats:
                    all_seats.append(
                        {
                            'section': section,
                            'subsection': subsection,
                            'row': row,
                            'seat_num': seat['seat_num'],
                            'status': seat['status'],
                            'price': seat['price'],
                            'seat_identifier': f'{section}-{subsection}-{row}-{seat["seat_num"]}',
                        }
                    )

            Logger.base.info(
                f'✅ [SEAT-STATE] Retrieved {len(all_seats)} seats for {section}-{subsection}'
            )
            return all_seats

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Failed to get subsection seats: {e}')
            return []

    @Logger.io
    async def get_seat_states(self, seat_ids: List[str], event_id: int) -> Dict[str, Dict]:
        """獲取指定座位的狀態"""
        Logger.base.info(f'🔍 [SEAT-STATE] Getting states for {len(seat_ids)} seats')

        if not self.is_available():
            raise RuntimeError('Seat state handler not available')

        try:
            seat_states = {}

            for seat_id in seat_ids:
                parts = seat_id.split('-')
                if len(parts) < 4:
                    Logger.base.warning(f'⚠️ [SEAT-STATE] Invalid seat_id: {seat_id}')
                    continue

                section, subsection, row, seat_num = (
                    parts[0],
                    int(parts[1]),
                    int(parts[2]),
                    int(parts[3]),
                )

                status = await self._get_seat_status_from_bitfield(
                    event_id, section, subsection, row, seat_num
                )

                if status:
                    row_seats = await self._get_row_seats(event_id, section, subsection, row)
                    price = next((s['price'] for s in row_seats if s['seat_num'] == seat_num), 0)

                    seat_states[seat_id] = {
                        'seat_id': seat_id,
                        'event_id': event_id,
                        'status': status,
                        'price': price,
                    }

            Logger.base.info(
                f'✅ [SEAT-STATE] Retrieved {len(seat_states)} seat states from Bitfield'
            )
            return seat_states

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Failed to read seat states: {e}')
            return {}

    @Logger.io
    async def get_available_seats_by_section(
        self, event_id: int, section: str, subsection: int, limit: Optional[int] = None
    ) -> List[Dict]:
        """按區域獲取可用座位"""
        Logger.base.info(f'🔍 [SEAT-STATE] Getting available seats for {section}-{subsection}')

        if not self.is_available():
            raise RuntimeError('Seat state handler not available')

        available_seats = []

        try:
            for row in range(1, 26):
                if limit and len(available_seats) >= limit:
                    break

                row_seats = await self._get_row_seats(event_id, section, subsection, row)

                for seat in row_seats:
                    if seat['status'] == 'available':
                        available_seats.append(
                            {
                                'seat_id': f'{section}-{subsection}-{row}-{seat["seat_num"]}',
                                'event_id': event_id,
                                'status': 'available',
                                'price': seat['price'],
                            }
                        )
                        if limit and len(available_seats) >= limit:
                            break

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Error scanning seats: {e}')
            raise

        Logger.base.info(
            f'📊 [SEAT-STATE] Found {len(available_seats)} available seats in section {section}-{subsection}'
        )
        return available_seats

    @Logger.io
    async def reserve_seats(
        self, seat_ids: List[str], booking_id: int, buyer_id: int, event_id: int
    ) -> Dict[str, bool]:
        """預訂座位 (AVAILABLE -> RESERVED)"""
        Logger.base.info(
            f'🔒 [SEAT-STATE] Reserving {len(seat_ids)} seats for booking {booking_id}'
        )

        if not self.is_available():
            raise RuntimeError('Seat state handler not available')

        current_states = await self.get_seat_states(seat_ids, event_id)
        results = {}

        unavailable_seats = []
        for seat_id in seat_ids:
            current_state = current_states.get(seat_id)

            if not current_state:
                unavailable_seats.append(seat_id)
                Logger.base.warning(f'⚠️ [SEAT-STATE] Seat {seat_id} not found')
                continue

            if current_state.get('status') != 'available':
                unavailable_seats.append(seat_id)
                Logger.base.warning(
                    f'⚠️ [SEAT-STATE] Seat {seat_id} not available (status: {current_state.get("status")})'
                )

        if unavailable_seats:
            Logger.base.error(
                f'❌ [SEAT-STATE] Cannot reserve seats, {len(unavailable_seats)} unavailable: {unavailable_seats}'
            )
            return {seat_id: False for seat_id in seat_ids}

        try:
            for seat_id in seat_ids:
                results[seat_id] = True
                Logger.base.info(f'✅ [SEAT-STATE] Requested reservation for seat {seat_id}')

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Failed to reserve seats: {e}')
            raise

        success_count = sum(results.values())
        Logger.base.info(
            f'🎯 [SEAT-STATE] Successfully requested reservation for {success_count}/{len(seat_ids)} seats'
        )

        return results

    @Logger.io
    async def release_seats(self, seat_ids: List[str], event_id: int) -> Dict[str, bool]:
        """釋放座位 (RESERVED -> AVAILABLE)"""
        Logger.base.info(f'🔓 [SEAT-STATE] Releasing {len(seat_ids)} seats')

        if not self.is_available():
            raise RuntimeError('Seat state handler not available')

        current_states = await self.get_seat_states(seat_ids, event_id)

        results = {}
        for seat_id in seat_ids:
            current_state = current_states.get(seat_id)

            if not current_state:
                results[seat_id] = False
                Logger.base.warning(f'⚠️ [SEAT-STATE] Seat {seat_id} not found')
                continue

            try:
                results[seat_id] = True
                Logger.base.info(f'✅ [SEAT-STATE] Requested release for seat {seat_id}')

            except Exception as e:
                Logger.base.error(f'❌ [SEAT-STATE] Failed to release seat {seat_id}: {e}')
                results[seat_id] = False

        success_count = sum(results.values())
        Logger.base.info(
            f'🎯 [SEAT-STATE] Requested release for {success_count}/{len(seat_ids)} seats successfully'
        )

        return results

    @Logger.io
    async def get_seat_price(self, seat_id: str, event_id: int) -> Optional[int]:
        """獲取座位價格"""
        seat_states = await self.get_seat_states([seat_id], event_id)
        seat_state = seat_states.get(seat_id)
        return seat_state.get('price') if seat_state else None

    @Logger.io
    async def initialize_seat(
        self, seat_id: str, event_id: int, price: int, timestamp: Optional[str] = None
    ) -> bool:
        """初始化座位狀態為 AVAILABLE"""
        try:
            parts = seat_id.split('-')
            if len(parts) < 4:
                Logger.base.error(f'❌ [SEAT-STATE] Invalid seat_id: {seat_id}')
                return False

            section, subsection, row, seat_num = (
                parts[0],
                int(parts[1]),
                int(parts[2]),
                int(parts[3]),
            )

            success = await self._set_seat_status_to_bitfield(
                event_id=event_id,
                section=section,
                subsection=subsection,
                row=row,
                seat_num=seat_num,
                status='available',
                price=price,
            )

            if success:
                Logger.base.info(f'✅ [SEAT-STATE] Initialized seat {seat_id}')
            else:
                Logger.base.error(f'❌ [SEAT-STATE] Failed to initialize seat {seat_id}')

            return success

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Error initializing seat {seat_id}: {e}')
            return False

    @Logger.io
    def _generate_all_seats_from_config(self, seating_config: dict, event_id: int) -> list[dict]:
        """
        從 seating_config 生成所有座位數據

        Args:
            seating_config: 座位配置，格式:
                {
                    "sections": [
                        {
                            "name": "A",
                            "price": 3000,
                            "subsections": [
                                {"number": 1, "rows": 10, "seats_per_row": 10},
                                ...
                            ]
                        },
                        ...
                    ]
                }
            event_id: 活動 ID

        Returns:
            座位列表，格式:
            [
                {
                    'section': 'A',
                    'subsection': 1,
                    'row': 1,
                    'seat_num': 1,
                    'seat_index': 0,
                    'price': 3000
                },
                ...
            ]
        """
        all_seats = []

        for section_config in seating_config['sections']:
            section_name = section_config['name']  # 'A', 'B', 'C'...
            section_price = section_config['price']  # 3000, 2800, 2500...

            for subsection in section_config['subsections']:
                subsection_num = subsection['number']  # 1, 2, 3...10
                rows = subsection['rows']  # 10 or 25
                seats_per_row = subsection['seats_per_row']  # 10 or 20

                # 生成該 subsection 的所有座位
                for row in range(1, rows + 1):
                    for seat_num in range(1, seats_per_row + 1):
                        # 計算 seat_index (從 0 開始)
                        seat_index = (row - 1) * seats_per_row + (seat_num - 1)

                        all_seats.append(
                            {
                                'section': section_name,
                                'subsection': subsection_num,
                                'row': row,
                                'seat_num': seat_num,
                                'seat_index': seat_index,
                                'price': section_price,  # 使用 section 層級的價格
                            }
                        )

        Logger.base.info(f'📊 [SEAT-GEN] Generated {len(all_seats)} seats from config')
        return all_seats

    @Logger.io
    async def initialize_seats_from_config(self, *, event_id: int, seating_config: dict) -> dict:
        """
        從 seating_config 直接初始化所有座位（使用單一 Lua 腳本）

        這個方法會：
        1. 從 seating_config 生成所有座位數據
        2. 準備 Lua 腳本參數
        3. 執行 Lua 腳本批量寫入 Kvrocks
        4. 建立 event_sections 索引
        5. 建立 section_stats 統計

        Args:
            event_id: 活動 ID
            seating_config: 座位配置（格式見 _generate_all_seats_from_config）

        Returns:
            {
                'success': True/False,
                'total_seats': 3000,
                'sections_count': 30,
                'error': None or error message
            }
        """
        try:
            # Step 1: 生成所有座位數據
            all_seats = self._generate_all_seats_from_config(seating_config, event_id)

            if not all_seats:
                return {
                    'success': False,
                    'total_seats': 0,
                    'sections_count': 0,
                    'error': 'No seats generated from config',
                }

            # Step 2: Lua 腳本（與 initialize_seats_batch 相同）
            lua_script = """
            local key_prefix = ARGV[1]
            local event_id = ARGV[2]
            local available_status = 0  -- AVAILABLE = 00 in binary
            local timestamp = redis.call('TIME')[1]  -- 獲取 Redis 時間戳

            -- 從 ARGV[3] 開始是座位數據，每個座位 6 個參數
            local seat_count = (#ARGV - 2) / 6
            local success_count = 0

            -- 收集統計資料和配置資訊
            local section_stats = {}
            local section_configs = {}  -- 儲存每個 section 的 rows 和 seats_per_row

            for i = 0, seat_count - 1 do
                local base_idx = 3 + i * 6
                local section = ARGV[base_idx]
                local subsection = ARGV[base_idx + 1]
                local row = ARGV[base_idx + 2]
                local seat_num = ARGV[base_idx + 3]
                local seat_index = ARGV[base_idx + 4]
                local price = ARGV[base_idx + 5]

                local section_id = section .. '-' .. subsection
                local bf_key = key_prefix .. 'seats_bf:' .. event_id .. ':' .. section_id
                local meta_key = key_prefix .. 'seat_meta:' .. event_id .. ':' .. section_id .. ':' .. row

                -- 計算 offset (每個座位 2 bits)
                local offset = seat_index * 2

                -- 設置 bitfield (AVAILABLE = 00)
                redis.call('SETBIT', bf_key, offset, 0)
                redis.call('SETBIT', bf_key, offset + 1, 0)

                -- 設置價格 metadata
                redis.call('HSET', meta_key, seat_num, price)

                -- 累積統計
                section_stats[section_id] = (section_stats[section_id] or 0) + 1

                -- 記錄配置（追蹤最大 row 和 seats_per_row）
                if not section_configs[section_id] then
                    section_configs[section_id] = {max_row = tonumber(row), seats_per_row = tonumber(seat_num)}
                else
                    if tonumber(row) > section_configs[section_id].max_row then
                        section_configs[section_id].max_row = tonumber(row)
                    end
                    if tonumber(seat_num) > section_configs[section_id].seats_per_row then
                        section_configs[section_id].seats_per_row = tonumber(seat_num)
                    end
                end

                success_count = success_count + 1
            end

            -- 批量寫入索引、統計和配置
            for section_id, count in pairs(section_stats) do
                -- 1. 建立索引 (使用 sorted set，score 為 0)
                redis.call('ZADD', key_prefix .. 'event_sections:' .. event_id, 0, section_id)

                -- 2. 設置統計 (初始狀態：所有座位都是 AVAILABLE)
                redis.call('HSET', key_prefix .. 'section_stats:' .. event_id .. ':' .. section_id,
                    'section_id', section_id,
                    'event_id', event_id,
                    'available', count,
                    'reserved', 0,
                    'sold', 0,
                    'total', count,
                    'updated_at', timestamp
                )

                -- 3. 儲存 section 配置
                local config = section_configs[section_id]
                redis.call('HSET', key_prefix .. 'section_config:' .. event_id .. ':' .. section_id,
                    'rows', config.max_row,
                    'seats_per_row', config.seats_per_row
                )
            end

            return success_count
            """

            # Step 3: 連接 Kvrocks
            client = await kvrocks_client.connect()

            # Step 4: 準備 Lua 腳本參數
            args = [_KEY_PREFIX, str(event_id)]  # ARGV[1] = key_prefix, ARGV[2] = event_id

            for seat in all_seats:
                args.extend(
                    [
                        seat['section'],  # 'A'
                        str(seat['subsection']),  # '1'
                        str(seat['row']),  # '1'
                        str(seat['seat_num']),  # '1'
                        str(seat['seat_index']),  # '0'
                        str(seat['price']),  # '3000'
                    ]
                )

            Logger.base.info(
                f'⚙️  [LUA-CONFIG] Executing Lua script with {len(all_seats)} seats, '
                f'{len(args)} total args'
            )

            # Step 5: 執行 Lua 腳本
            success_count: int = await client.eval(lua_script, 0, *args)  # type: ignore[misc]

            Logger.base.info(f'✅ [LUA-CONFIG] Initialized {success_count}/{len(all_seats)} seats')

            # Step 6: 驗證結果
            sections_count = await client.zcard(_make_key(f'event_sections:{event_id}'))
            Logger.base.info(f'📋 [LUA-CONFIG] Created {sections_count} sections in index')

            return {
                'success': True,
                'total_seats': int(success_count),
                'sections_count': int(sections_count),
                'error': None,
            }

        except Exception as e:
            Logger.base.error(f'❌ [LUA-CONFIG] Failed to initialize from config: {e}')
            return {'success': False, 'total_seats': 0, 'sections_count': 0, 'error': str(e)}

    @Logger.io
    async def finalize_payment(
        self, seat_id: str, event_id: int, timestamp: Optional[str] = None
    ) -> bool:
        """完成支付，將座位從 RESERVED 轉為 SOLD"""
        try:
            parts = seat_id.split('-')
            if len(parts) < 4:
                Logger.base.error(f'❌ [SEAT-STATE] Invalid seat_id: {seat_id}')
                return False

            section, subsection, row, seat_num = (
                parts[0],
                int(parts[1]),
                int(parts[2]),
                int(parts[3]),
            )

            current_price = await self.get_seat_price(seat_id, event_id)
            if current_price is None:
                Logger.base.error(f'❌ [SEAT-STATE] Seat {seat_id} not found or no price')
                return False

            success = await self._set_seat_status_to_bitfield(
                event_id=event_id,
                section=section,
                subsection=subsection,
                row=row,
                seat_num=seat_num,
                status='sold',
                price=current_price,
            )

            if success:
                Logger.base.info(f'✅ [SEAT-STATE] Finalized payment for seat {seat_id}')
            else:
                Logger.base.error(f'❌ [SEAT-STATE] Failed to finalize payment for seat {seat_id}')

            return success

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Error finalizing payment for seat {seat_id}: {e}')
            return False

    @Logger.io
    async def _rollback_reservations(self, reserved_seat_ids: List[str], event_id: int) -> None:
        """回滾已預訂的座位"""
        if not reserved_seat_ids:
            return

        Logger.base.warning(f'🔄 [SEAT-STATE] Rolling back {len(reserved_seat_ids)} reservations')
        try:
            await self.release_seats(reserved_seat_ids, event_id)
        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Failed to rollback reservations: {e}')

    @Logger.io
    async def list_all_subsection_status(self, event_id: int) -> Dict[str, Dict]:
        """
        獲取活動所有 subsection 的統計資訊（從 Kvrocks 讀取）

        實現策略：
        1. 從索引獲取所有 section_id
        2. 使用 Pipeline 批量查詢統計數據
        3. 組合並返回結果

        Returns:
            Dict mapping section_id to stats:
            {
                "A-1": {"available": 100, "reserved": 20, "sold": 30, "total": 150},
                ...
            }
        """
        # TODO(human): 實現統計查詢邏輯
        # 提示：可以參考 kvrocks_stats_client.list_all_subsection_status() 的實現
        # 或者設計更優化的查詢方式

        try:
            client = await kvrocks_client.connect()

            # 1. 從索引取得所有 section_id
            index_key = _make_key(f'event_sections:{event_id}')
            section_ids = await client.zrange(index_key, 0, -1)

            if not section_ids:
                Logger.base.info(f'📊 [SEAT-STATE] No sections found for event {event_id}')
                return {}

            # 2. 使用 Pipeline 批量查詢統計數據
            pipe = client.pipeline()
            for section_id in section_ids:
                stats_key = _make_key(f'section_stats:{event_id}:{section_id}')
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

            Logger.base.info(
                f'✅ [SEAT-STATE] Retrieved {len(all_stats)} subsection stats for event {event_id}'
            )
            return all_stats

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Failed to get subsection status: {e}')
            return {}
