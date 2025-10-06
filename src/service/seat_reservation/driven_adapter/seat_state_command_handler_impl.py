"""
Seat State Command Handler Implementation

座位狀態命令處理器實作 - CQRS Command Side
"""

import os
from typing import Dict, List, Optional

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.seat_reservation.app.interface.i_seat_state_command_handler import (
    ISeatStateCommandHandler,
)


# Get key prefix from environment for test isolation
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')


def _make_key(key: str) -> str:
    """Add prefix to key for test isolation in parallel testing"""
    return f'{_KEY_PREFIX}{key}'


# Lua script for atomic seat reservation with Check-and-Set pattern
RESERVE_SEATS_LUA_SCRIPT = """
local key_prefix = ARGV[1]
local event_id = ARGV[2]
local AVAILABLE = 0  -- 00 in binary
local RESERVED = 1   -- 01 in binary

-- Parse seat data: ARGV[3], ARGV[4], ... (section, subsection, row, seat, seat_index)
local seat_count = (#ARGV - 2) / 5
local results = {}
local section_changes = {}  -- Track stat changes per section

for i = 0, seat_count - 1 do
    local base_idx = 3 + i * 5
    local section = ARGV[base_idx]
    local subsection = ARGV[base_idx + 1]
    local row = ARGV[base_idx + 2]
    local seat = ARGV[base_idx + 3]
    local seat_index = tonumber(ARGV[base_idx + 4])

    local section_id = section .. '-' .. subsection
    local seat_id = section .. '-' .. subsection .. '-' .. row .. '-' .. seat
    local bf_key = key_prefix .. 'seats_bf:' .. event_id .. ':' .. section_id
    local offset = seat_index * 2

    -- Check current status (read 2 bits)
    local bit0 = redis.call('GETBIT', bf_key, offset)
    local bit1 = redis.call('GETBIT', bf_key, offset + 1)
    local current_status = bit0 * 2 + bit1

    -- Only reserve if AVAILABLE (00)
    if current_status == AVAILABLE then
        -- Set to RESERVED (01)
        redis.call('SETBIT', bf_key, offset, 1)
        redis.call('SETBIT', bf_key, offset + 1, 0)

        results[i + 1] = seat_id .. ':1'  -- success

        -- Track stat changes
        if not section_changes[section_id] then
            section_changes[section_id] = 0
        end
        section_changes[section_id] = section_changes[section_id] + 1
    else
        results[i + 1] = seat_id .. ':0'  -- failed (already reserved/sold)
    end
end

-- Update statistics atomically
local timestamp = redis.call('TIME')[1]
for section_id, count in pairs(section_changes) do
    local stats_key = key_prefix .. 'section_stats:' .. event_id .. ':' .. section_id
    redis.call('HINCRBY', stats_key, 'available', -count)
    redis.call('HINCRBY', stats_key, 'reserved', count)
    redis.call('HSET', stats_key, 'updated_at', timestamp)
end

return results
"""

# Status constants
SEAT_STATUS_AVAILABLE = 0  # 00
SEAT_STATUS_RESERVED = 1  # 01
SEAT_STATUS_SOLD = 2  # 10

STATUS_TO_BITFIELD = {
    'available': SEAT_STATUS_AVAILABLE,
    'reserved': SEAT_STATUS_RESERVED,
    'sold': SEAT_STATUS_SOLD,
}


class SeatStateCommandHandlerImpl(ISeatStateCommandHandler):
    """
    座位狀態命令處理器實作 (CQRS Command)

    職責：只負責寫入操作，修改座位狀態
    """

    @staticmethod
    def _calculate_seat_index(row: int, seat_num: int, seats_per_row: int) -> int:
        """計算座位在 Bitfield 中的 index"""
        return (row - 1) * seats_per_row + (seat_num - 1)

    @Logger.io
    async def _get_section_config(self, event_id: int, section_id: str) -> Dict:
        """從 Redis 獲取 section 配置信息"""
        try:
            client = await kvrocks_client.connect()
            config_key = _make_key(f'section_config:{event_id}:{section_id}')
            config = await client.hgetall(config_key)  # type: ignore

            if not config:
                raise ValueError(f'Section config not found: {section_id}')

            return {'rows': int(config['rows']), 'seats_per_row': int(config['seats_per_row'])}

        except Exception as e:
            Logger.base.error(f'❌ [CMD] Failed to get section config: {e}')
            raise

    @Logger.io
    async def reserve_seats(
        self, seat_ids: List[str], booking_id: int, buyer_id: int, event_id: int
    ) -> Dict[str, bool]:
        """
        預訂座位 (AVAILABLE -> RESERVED) - 使用 Lua script 確保原子性

        Exactly-Once 語義：
        - Check-and-Set: 只有 AVAILABLE 狀態才能改為 RESERVED
        - 同時更新 section statistics
        """
        Logger.base.info(f'🔒 [CMD] Reserving {len(seat_ids)} seats for booking {booking_id}')

        client = await kvrocks_client.connect()
        args = [_KEY_PREFIX, str(event_id)]

        # Parse seat_ids and prepare Lua script arguments
        for seat_id in seat_ids:
            parts = seat_id.split('-')
            if len(parts) != 4:
                Logger.base.warning(f'⚠️ Invalid seat_id format: {seat_id}')
                continue

            section, subsection, row, seat = parts
            section_id = f'{section}-{subsection}'

            # Get config to calculate seat_index
            config = await self._get_section_config(event_id, section_id)
            seats_per_row = config['seats_per_row']
            seat_index = self._calculate_seat_index(int(row), int(seat), seats_per_row)

            args.extend([section, subsection, row, seat, str(seat_index)])

        # Execute Lua script
        Logger.base.info('⚙️  [CMD] Executing atomic reserve Lua script')
        raw_results = await client.eval(RESERVE_SEATS_LUA_SCRIPT, 0, *args)  # type: ignore[misc]

        # Parse results
        results = {}
        for raw_result in raw_results:
            if isinstance(raw_result, bytes):
                raw_result = raw_result.decode('utf-8')

            seat_id, success = raw_result.split(':')
            results[seat_id] = success == '1'

        success_count = sum(results.values())
        Logger.base.info(f'🎯 [CMD] Reserved {success_count}/{len(seat_ids)} seats atomically')

        return results

    @Logger.io
    async def release_seats(self, seat_ids: List[str], event_id: int) -> Dict[str, bool]:
        """釋放座位 (RESERVED -> AVAILABLE)"""
        Logger.base.info(f'🔓 [CMD] Releasing {len(seat_ids)} seats')

        # TODO(human): Implement release logic with Lua script
        # Hint: Similar to reserve_seats but change RESERVED -> AVAILABLE
        results = {seat_id: True for seat_id in seat_ids}
        return results

    @Logger.io
    async def finalize_payment(
        self, seat_id: str, event_id: int, timestamp: Optional[str] = None
    ) -> bool:
        """完成支付 (RESERVED -> SOLD)"""
        Logger.base.info(f'💳 [CMD] Finalizing payment for seat {seat_id}')

        try:
            parts = seat_id.split('-')
            if len(parts) != 4:
                return False

            section, subsection, row, seat_num = parts
            section_id = f'{section}-{subsection}'

            config = await self._get_section_config(event_id, section_id)
            seats_per_row = config['seats_per_row']
            seat_index = self._calculate_seat_index(int(row), int(seat_num), seats_per_row)

            client = await kvrocks_client.connect()
            bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')
            offset = seat_index * 2

            # Set to SOLD (10)
            await client.setbit(bf_key, offset, 0)
            await client.setbit(bf_key, offset + 1, 1)

            Logger.base.info(f'✅ [CMD] Finalized payment for {seat_id}')
            return True

        except Exception as e:
            Logger.base.error(f'❌ [CMD] Failed to finalize payment: {e}')
            return False

    @Logger.io
    async def initialize_seat(
        self, seat_id: str, event_id: int, price: int, timestamp: Optional[str] = None
    ) -> bool:
        """初始化座位 (set to AVAILABLE)"""
        Logger.base.info(f'🆕 [CMD] Initializing seat {seat_id}')

        try:
            parts = seat_id.split('-')
            if len(parts) != 4:
                return False

            section, subsection, row, seat_num = parts
            section_id = f'{section}-{subsection}'

            config = await self._get_section_config(event_id, section_id)
            seats_per_row = config['seats_per_row']
            seat_index = self._calculate_seat_index(int(row), int(seat_num), seats_per_row)

            client = await kvrocks_client.connect()
            bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')
            meta_key = _make_key(f'seat_meta:{event_id}:{section_id}:{row}')
            offset = seat_index * 2

            # Set to AVAILABLE (00)
            await client.setbit(bf_key, offset, 0)
            await client.setbit(bf_key, offset + 1, 0)

            # Set price metadata
            client.hset(meta_key, str(seat_num), str(price))  # pyright: ignore

            Logger.base.info(f'✅ [CMD] Initialized seat {seat_id}')
            return True

        except Exception as e:
            Logger.base.error(f'❌ [CMD] Failed to initialize seat: {e}')
            return False
