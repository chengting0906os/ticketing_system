"""
Seat State Query Handler Implementation

座位狀態查詢處理器實作 - CQRS Query Side
"""

import os
from typing import Dict, List, Optional

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.seat_reservation.app.interface.i_seat_state_query_handler import (
    ISeatStateQueryHandler,
)


# Get key prefix from environment for test isolation
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')


def _make_key(key: str) -> str:
    """Add prefix to key for test isolation"""
    return f'{_KEY_PREFIX}{key}'


# Bitfield to status mapping
BITFIELD_TO_STATUS = {
    0: 'available',  # 00
    1: 'reserved',  # 01
    2: 'sold',  # 10
}


class SeatStateQueryHandlerImpl(ISeatStateQueryHandler):
    """
    座位狀態查詢處理器實作 (CQRS Query)

    職責：只負責讀取操作，不修改狀態
    """

    @staticmethod
    def _calculate_seat_index(row: int, seat_num: int, seats_per_row: int) -> int:
        """計算座位在 Bitfield 中的 index"""
        return (row - 1) * seats_per_row + (seat_num - 1)

    @Logger.io
    async def _get_section_config(self, event_id: int, section_id: str) -> Dict:
        """從 Redis 獲取 section 配置"""
        from src.platform.exception.exceptions import NotFoundError

        # Get client from initialized pool (no await needed)
        client = kvrocks_client.get_client()
        config_key = _make_key(f'section_config:{event_id}:{section_id}')
        config = await client.hgetall(config_key)  # type: ignore

        if not config:
            raise NotFoundError('Event not found')

        return {'rows': int(config['rows']), 'seats_per_row': int(config['seats_per_row'])}

    @Logger.io
    async def get_seat_states(self, seat_ids: List[str], event_id: int) -> Dict[str, Dict]:
        """獲取指定座位的狀態"""
        Logger.base.info(f'🔍 [QUERY] Getting states for {len(seat_ids)} seats')

        seat_states = {}
        # Get client from initialized pool (no await needed)
        client = kvrocks_client.get_client()

        for seat_id in seat_ids:
            parts = seat_id.split('-')
            if len(parts) != 4:
                continue

            section, subsection, row, seat_num = parts
            section_id = f'{section}-{subsection}'

            try:
                config = await self._get_section_config(event_id, section_id)
                seats_per_row = config['seats_per_row']
                seat_index = self._calculate_seat_index(int(row), int(seat_num), seats_per_row)

                bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')
                meta_key = _make_key(f'seat_meta:{event_id}:{section_id}:{row}')
                offset = seat_index * 2

                # Read status from bitfield
                bit0 = await client.getbit(bf_key, offset)
                bit1 = await client.getbit(bf_key, offset + 1)
                status_value = bit0 * 2 + bit1

                # Read price
                prices = await client.hgetall(meta_key)  # type: ignore
                price = int(prices.get(seat_num, 0)) if prices else 0

                seat_states[seat_id] = {
                    'seat_id': seat_id,
                    'event_id': event_id,
                    'status': BITFIELD_TO_STATUS.get(status_value, 'available'),
                    'price': price,
                }

            except Exception as e:
                Logger.base.error(f'❌ [QUERY] Failed to get state for {seat_id}: {e}')
                continue

        Logger.base.info(f'✅ [QUERY] Retrieved {len(seat_states)} seat states')
        return seat_states

    @Logger.io
    @Logger.io
    async def get_seat_price(self, seat_id: str, event_id: int) -> Optional[int]:
        """獲取座位價格"""
        seat_states = await self.get_seat_states([seat_id], event_id)
        seat_state = seat_states.get(seat_id)
        return seat_state.get('price') if seat_state else None

    @Logger.io
    async def list_all_subsection_status(self, event_id: int) -> Dict[str, Dict]:
        """獲取活動所有 subsection 的統計資訊"""
        Logger.base.info(f'📊 [QUERY] Listing all subsection status for event {event_id}')

        # Get client from initialized pool (no await needed)
        client = kvrocks_client.get_client()

        # Get all section IDs from index
        index_key = _make_key(f'event_sections:{event_id}')
        section_ids = await client.zrange(index_key, 0, -1)

        if not section_ids:
            return {}

        # Batch query statistics using pipeline
        pipe = client.pipeline()
        for section_id in section_ids:
            stats_key = _make_key(f'section_stats:{event_id}:{section_id}')
            pipe.hgetall(stats_key)

        results = await pipe.execute()

        # Parse results
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

        Logger.base.info(f'✅ [QUERY] Retrieved {len(all_stats)} subsection stats')
        return all_stats

    @Logger.io
    async def list_all_subsection_seats(
        self, event_id: int, section: str, subsection: int
    ) -> List[Dict]:
        """獲取指定 subsection 的所有座位（包括 available, reserved, sold）"""
        Logger.base.info(
            f'📊 [QUERY] Listing all seats for event {event_id}, section {section}-{subsection}'
        )

        section_id = f'{section}-{subsection}'
        config = await self._get_section_config(event_id, section_id)
        total_rows = config['rows']
        seats_per_row = config['seats_per_row']

        # Get client from initialized pool (no await needed)
        client = kvrocks_client.get_client()
        bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')

        all_seats = []

        for row in range(1, total_rows + 1):
            meta_key = _make_key(f'seat_meta:{event_id}:{section_id}:{row}')
            prices = await client.hgetall(meta_key)  # type: ignore

            for seat_num in range(1, seats_per_row + 1):
                seat_index = self._calculate_seat_index(row, seat_num, seats_per_row)
                offset = seat_index * 2

                # Read status from bitfield
                bit0 = await client.getbit(bf_key, offset)
                bit1 = await client.getbit(bf_key, offset + 1)
                status_value = bit0 * 2 + bit1

                seat_identifier = f'{section}-{subsection}-{row}-{seat_num}'
                all_seats.append(
                    {
                        'section': section,
                        'subsection': subsection,
                        'row': row,
                        'seat_num': seat_num,
                        'price': int(prices.get(str(seat_num), 0)) if prices else 0,
                        'status': BITFIELD_TO_STATUS.get(status_value, 'available'),
                        'seat_identifier': seat_identifier,
                    }
                )

        Logger.base.info(f'✅ [QUERY] Retrieved {len(all_seats)} seats for section {section_id}')
        return all_seats
