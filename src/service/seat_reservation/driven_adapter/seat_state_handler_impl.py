"""
Seat State Handler Implementation
座位狀態處理器實現 - 直接使用 Kvrocks Bitfield + Counter
"""

from typing import Dict, List, Optional

from async_lru import alru_cache

from src.platform.logging.loguru_io import Logger
from src.platform.state.redis_client import kvrocks_client
from src.service.seat_reservation.app.interface.i_seat_state_handler import SeatStateHandler


# 座位狀態編碼 (2 bits)
SEAT_STATUS_AVAILABLE = 0  # 0b00
SEAT_STATUS_RESERVED = 1  # 0b01
SEAT_STATUS_SOLD = 2  # 0b10

STATUS_TO_BITFIELD = {
    'AVAILABLE': SEAT_STATUS_AVAILABLE,
    'RESERVED': SEAT_STATUS_RESERVED,
    'SOLD': SEAT_STATUS_SOLD,
}

BITFIELD_TO_STATUS = {
    SEAT_STATUS_AVAILABLE: 'AVAILABLE',
    SEAT_STATUS_RESERVED: 'RESERVED',
    SEAT_STATUS_SOLD: 'SOLD',
}


class SeatStateHandlerImpl(SeatStateHandler):
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

    @alru_cache(maxsize=1000)
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
            return False

    def is_available(self) -> bool:
        """檢查服務是否可用"""
        return True

    async def _get_seat_status_from_bitfield(
        self, event_id: int, section: str, subsection: int, row: int, seat_num: int
    ) -> Optional[str]:
        """從 Bitfield 讀取單個座位狀態"""
        try:
            client = await kvrocks_client.connect()
            section_id = f'{section}-{subsection}'
            bf_key = f'seats_bf:{event_id}:{section_id}'

            seat_index = self._calculate_seat_index(row, seat_num)
            offset = seat_index * 2

            value = await client.getbit(bf_key, offset) * 2 + await client.getbit(
                bf_key, offset + 1
            )
            return BITFIELD_TO_STATUS.get(value, 'AVAILABLE')

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Failed to get seat status: {e}')
            return None

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
            bf_key = f'seats_bf:{event_id}:{section_id}'
            meta_key = f'seat_meta:{event_id}:{section_id}:{row}'

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
            bf_key = f'seats_bf:{event_id}:{section_id}'
            meta_key = f'seat_meta:{event_id}:{section_id}:{row}'

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
                        'status': BITFIELD_TO_STATUS.get(value, 'AVAILABLE'),
                        'price': int(prices.get(str(seat_num), 0)) if prices else 0,
                    }
                )

            return seats

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Failed to get row seats: {e}')
            return []

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
                    if seat['status'] == 'AVAILABLE':
                        available_seats.append(
                            {
                                'seat_id': f'{section}-{subsection}-{row}-{seat["seat_num"]}',
                                'event_id': event_id,
                                'status': 'AVAILABLE',
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

            if current_state.get('status') != 'AVAILABLE':
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

    async def get_seat_price(self, seat_id: str, event_id: int) -> Optional[int]:
        """獲取座位價格"""
        seat_states = await self.get_seat_states([seat_id], event_id)
        seat_state = seat_states.get(seat_id)
        return seat_state.get('price') if seat_state else None

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
                status='AVAILABLE',
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

    async def initialize_seats_batch(self, seats: list[dict]) -> dict[str, bool]:
        """批量初始化座位狀態為 AVAILABLE - 使用 Lua 腳本"""
        results = {}
        if not seats:
            return results

        # Lua 腳本：批量設置 bitfield 和 metadata
        lua_script = """
        local event_id = ARGV[1]
        local available_status = 0  -- AVAILABLE = 00 in binary
        
        -- 從 ARGV[2] 開始是座位數據，每個座位 6 個參數
        local seat_count = (#ARGV - 1) / 6
        local success_count = 0
        
        for i = 0, seat_count - 1 do
            local base_idx = 2 + i * 6
            local section = ARGV[base_idx]
            local subsection = ARGV[base_idx + 1]
            local row = ARGV[base_idx + 2]
            local seat_num = ARGV[base_idx + 3]
            local seat_index = ARGV[base_idx + 4]
            local price = ARGV[base_idx + 5]
            
            local section_id = section .. '-' .. subsection
            local bf_key = 'seats_bf:' .. event_id .. ':' .. section_id
            local meta_key = 'seat_meta:' .. event_id .. ':' .. section_id .. ':' .. row
            
            -- 計算 offset (每個座位 2 bits)
            local offset = seat_index * 2
            
            -- 設置 bitfield (AVAILABLE = 00)
            redis.call('SETBIT', bf_key, offset, 0)
            redis.call('SETBIT', bf_key, offset + 1, 0)
            
            -- 設置價格 metadata
            redis.call('HSET', meta_key, seat_num, price)
            
            success_count = success_count + 1
        end
        
        return success_count
        """

        try:
            client = await kvrocks_client.connect()

            # 準備 Lua 腳本參數
            args = [str(seats[0]['event_id'])]  # ARGV[1] = event_id

            for seat_data in seats:
                seat_id = seat_data['seat_id']
                try:
                    parts = seat_id.split('-')
                    if len(parts) < 4:
                        results[seat_id] = False
                        continue

                    section, subsection, row, seat_num = (
                        parts[0],
                        int(parts[1]),
                        int(parts[2]),
                        int(parts[3]),
                    )
                    price = seat_data['price']

                    # 計算 seat_index
                    seat_index = self._calculate_seat_index(row, seat_num)

                    # 添加 6 個參數到 ARGV
                    args.extend(
                        [
                            section,
                            str(subsection),
                            str(row),
                            str(seat_num),
                            str(seat_index),
                            str(price),
                        ]
                    )

                except Exception as e:
                    Logger.base.error(f'❌ [LUA-INIT] Error preparing {seat_id}: {e}')
                    results[seat_id] = False

            # 執行 Lua 腳本
            success_count = client.eval(lua_script, 0, *args)

            # 標記成功的座位
            for seat_data in seats:
                seat_id = seat_data['seat_id']
                if seat_id not in results:
                    results[seat_id] = True

            Logger.base.info(
                f'✅ [LUA-INIT] Lua script initialized {success_count}/{len(seats)} seats'
            )
            return results

        except Exception as e:
            Logger.base.error(f'❌ [LUA-INIT] Lua execution failed: {e}')
            # 全部標記失敗
            for seat_data in seats:
                results[seat_data['seat_id']] = False
            return results

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
                status='SOLD',
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

    async def _rollback_reservations(self, reserved_seat_ids: List[str], event_id: int) -> None:
        """回滾已預訂的座位"""
        if not reserved_seat_ids:
            return

        Logger.base.warning(f'🔄 [SEAT-STATE] Rolling back {len(reserved_seat_ids)} reservations')
        try:
            await self.release_seats(reserved_seat_ids, event_id)
        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Failed to rollback reservations: {e}')
