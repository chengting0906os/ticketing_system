"""
Seat State Command Handler Implementation

座位狀態命令處理器實作 - CQRS Command Side
"""

import os
from typing import Dict, List, Optional

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.shared_kernel.app.interface import ISeatStateCommandHandler
from src.service.seat_reservation.driven_adapter.lua_script import RESERVE_SEATS_SCRIPT


# Get key prefix from environment for test isolation
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')


def _make_key(key: str) -> str:
    """Add prefix to key for test isolation in parallel testing"""
    return f'{_KEY_PREFIX}{key}'


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
            client = kvrocks_client.get_client()
            config_key = _make_key(f'section_config:{event_id}:{section_id}')
            config = await client.hgetall(config_key)  # type: ignore

            if not config:
                raise ValueError(f'Section config not found: {section_id}')

            return {'rows': int(config['rows']), 'seats_per_row': int(config['seats_per_row'])}

        except Exception as e:
            Logger.base.error(f'❌ [CMD] Failed to get section config: {e}')
            raise

    @Logger.io
    async def reserve_seats_atomic(
        self,
        *,
        event_id: int,
        booking_id: int,
        buyer_id: int,
        mode: str,
        seat_ids: Optional[List[str]] = None,
        section: Optional[str] = None,
        subsection: Optional[int] = None,
        quantity: Optional[int] = None,
    ) -> Dict:
        """
        原子性預訂座位 - 統一接口，由 Lua 腳本根據 mode 分流

        支持兩種模式：
        1. manual: 預訂指定座位
        2. best_available: 自動查找並預訂連續座位
        """
        Logger.base.info(f'🎯 [CMD] Reserving seats (mode={mode}) for booking {booking_id}')

        client = kvrocks_client.get_client()

        if mode == 'manual':
            # Manual mode: 準備指定座位的參數
            if not seat_ids:
                return {
                    'success': False,
                    'reserved_seats': [],
                    'error_message': 'Manual mode requires seat_ids',
                }

            if not section or subsection is None:
                return {
                    'success': False,
                    'reserved_seats': [],
                    'error_message': 'Manual mode requires section and subsection',
                }

            args = [_KEY_PREFIX, str(event_id), str(booking_id), 'manual']  # 🆕 添加 booking_id
            section_id = f'{section}-{subsection}'

            # Get config to calculate seat_index
            config = await self._get_section_config(event_id, section_id)
            seats_per_row = config['seats_per_row']

            # Parse seat_ids and prepare Lua script arguments
            for seat_id in seat_ids:
                parts = seat_id.split('-')

                if len(parts) == 2:
                    # 2-part format from ticketing domain: "row-seat"
                    # Combine with section and subsection parameters
                    row, seat = parts
                    Logger.base.info(
                        f'📍 [CMD] Processing seat: {section}-{subsection}-{row}-{seat} (from {seat_id})'
                    )

                    # Calculate seat_index
                    seat_index = self._calculate_seat_index(int(row), int(seat), seats_per_row)
                    args.extend([section, str(subsection), row, seat, str(seat_index)])

                elif len(parts) == 4:
                    # 4-part format: "section-subsection-row-seat" (backward compatibility)
                    sec, subsec, row, seat = parts
                    Logger.base.info(
                        f'📍 [CMD] Processing seat: {sec}-{subsec}-{row}-{seat} (4-part format)'
                    )

                    # Calculate seat_index
                    seat_index = self._calculate_seat_index(int(row), int(seat), seats_per_row)
                    args.extend([sec, subsec, row, seat, str(seat_index)])
                else:
                    Logger.base.warning(
                        f'⚠️ Invalid seat_id format: {seat_id} (expected row-seat or section-subsection-row-seat)'
                    )
                    continue

            # Execute Lua script
            Logger.base.info('⚙️ [CMD] Executing manual mode Lua script')
            raw_results = await client.eval(RESERVE_SEATS_SCRIPT, 0, *args)  # type: ignore[misc]

            # Parse results (manual mode returns array of "seat_id:success")
            results = {}
            for raw_result in raw_results:
                if isinstance(raw_result, bytes):
                    raw_result = raw_result.decode('utf-8')

                seat_id, success = raw_result.split(':')
                results[seat_id] = success == '1'

            successful_seats = [sid for sid, succ in results.items() if succ]
            failed_seats = [sid for sid, succ in results.items() if not succ]

            if failed_seats:
                Logger.base.warning(f'⚠️ [CMD] Some seats unavailable: {failed_seats}')
                return {
                    'success': False,
                    'reserved_seats': successful_seats,
                    'error_message': f'Some seats are not available: {failed_seats}',
                }

            # Get price from Kvrocks seat_meta (all seats in same subsection have same price)
            # Fetch from first seat's row
            if successful_seats:
                first_seat = successful_seats[0]
                parts = first_seat.split('-')
                if len(parts) == 4:
                    _, _, row, seat_num = parts
                    meta_key = _make_key(f'seat_meta:{event_id}:{section_id}:{row}')
                    prices = await client.hgetall(meta_key)  # type: ignore
                    ticket_price = int(prices.get(seat_num, 0)) if prices else 0
                else:
                    ticket_price = 0
            else:
                ticket_price = 0

            Logger.base.info(
                f'✅ [CMD] Reserved {len(successful_seats)} seats (manual), price={ticket_price}'
            )
            return {
                'success': True,
                'reserved_seats': successful_seats,
                'ticket_price': ticket_price,
                'error_message': None,
            }

        elif mode == 'best_available':
            # Best available mode: 準備自動查找連續座位的參數
            if not section or subsection is None or not quantity:
                return {
                    'success': False,
                    'reserved_seats': [],
                    'error_message': 'Best available mode requires section, subsection, and quantity',
                }

            section_id = f'{section}-{subsection}'

            # Get section config
            config = await self._get_section_config(event_id, section_id)
            rows = config['rows']
            seats_per_row = config['seats_per_row']

            args = [
                _KEY_PREFIX,
                str(event_id),
                str(booking_id),  # 🆕 添加 booking_id
                'best_available',
                section_id,
                str(quantity),
                str(rows),
                str(seats_per_row),
            ]

            # Execute Lua script
            Logger.base.info('⚙️ [CMD] Executing best_available mode Lua script')
            raw_result = await client.eval(RESERVE_SEATS_SCRIPT, 0, *args)  # type: ignore[misc]

            # Parse result (best_available returns "success:seat1,seat2,..." or "error:message")
            if isinstance(raw_result, bytes):
                raw_result = raw_result.decode('utf-8')

            if raw_result.startswith('success:'):
                seat_ids_str = raw_result.split(':', 1)[1]
                reserved_seats = seat_ids_str.split(',') if seat_ids_str else []

                # Get price from Kvrocks seat_meta (all seats in same subsection have same price)
                if reserved_seats:
                    first_seat = reserved_seats[0]
                    parts = first_seat.split('-')
                    if len(parts) == 4:
                        _, _, row, seat_num = parts
                        meta_key = _make_key(f'seat_meta:{event_id}:{section_id}:{row}')
                        prices = await client.hgetall(meta_key)  # type: ignore
                        ticket_price = int(prices.get(seat_num, 0)) if prices else 0
                    else:
                        ticket_price = 0
                else:
                    ticket_price = 0

                Logger.base.info(
                    f'✅ [CMD] Reserved {len(reserved_seats)} consecutive seats (best_available), price={ticket_price}'
                )
                return {
                    'success': True,
                    'reserved_seats': reserved_seats,
                    'ticket_price': ticket_price,
                    'error_message': None,
                }

            elif raw_result.startswith('error:'):
                error_msg = raw_result.split(':', 1)[1]
                Logger.base.warning(f'⚠️ [CMD] {error_msg}')
                return {
                    'success': False,
                    'reserved_seats': [],
                    'error_message': error_msg,
                }

            else:
                Logger.base.error(f'❌ [CMD] Unexpected Lua result: {raw_result}')
                return {
                    'success': False,
                    'reserved_seats': [],
                    'error_message': 'Unexpected script result',
                }

        else:
            return {
                'success': False,
                'reserved_seats': [],
                'error_message': f'Invalid mode: {mode}',
            }

    @Logger.io
    async def find_and_reserve_consecutive_seats(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        quantity: int,
        booking_id: int,
        buyer_id: int,
    ) -> Dict:
        """
        自動找出連續座位並預訂 (best_available mode)

        使用 Lua script 原子性地：
        1. 掃描 section 的所有排
        2. 找出第一組連續可用座位
        3. 立即預訂這些座位

        Returns:
            Dict with 'success', 'reserved_seats', 'error_message' keys
        """
        Logger.base.info(
            f'🎯 [CMD] Finding {quantity} consecutive seats in {section}-{subsection} '
            f'for booking {booking_id}'
        )

        section_id = f'{section}-{subsection}'

        # Get section config for rows and seats_per_row
        config = await self._get_section_config(event_id, section_id)
        rows = config['rows']
        seats_per_row = config['seats_per_row']

        # Call Lua script in best_available mode
        client = kvrocks_client.get_client()
        args = [
            _KEY_PREFIX,
            str(event_id),
            str(booking_id),  # 🆕 添加 booking_id
            'best_available',
            section_id,
            str(quantity),
            str(rows),
            str(seats_per_row),
        ]

        Logger.base.info('⚙️  [CMD] Executing find consecutive seats Lua script')
        raw_result = await client.eval(RESERVE_SEATS_SCRIPT, 0, *args)  # type: ignore[misc]

        # Parse result
        if isinstance(raw_result, bytes):
            raw_result = raw_result.decode('utf-8')

        if raw_result.startswith('success:'):
            seat_ids_str = raw_result.split(':', 1)[1]
            reserved_seats = seat_ids_str.split(',') if seat_ids_str else []

            Logger.base.info(
                f'✅ [CMD] Found and reserved {len(reserved_seats)} consecutive seats: {reserved_seats}'
            )

            return {
                'success': True,
                'reserved_seats': reserved_seats,
                'error_message': None,
            }
        elif raw_result.startswith('error:'):
            error_msg = raw_result.split(':', 1)[1]
            Logger.base.warning(f'⚠️ [CMD] Failed to find consecutive seats: {error_msg}')

            return {
                'success': False,
                'reserved_seats': [],
                'error_message': error_msg,
            }
        else:
            Logger.base.error(f'❌ [CMD] Unexpected Lua script result: {raw_result}')
            return {
                'success': False,
                'reserved_seats': [],
                'error_message': 'Unexpected script result',
            }

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

            client = kvrocks_client.get_client()
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

            client = kvrocks_client.get_client()
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
