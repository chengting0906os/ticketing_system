"""
Seat State Query Handler Implementation

座位狀態查詢處理器實作 - CQRS Query Side

Cache Strategy (Polling-based):
- Background task polls Kvrocks every 0.5s to refresh all seat stats
- Query methods can optionally read from in-memory cache
- Eventually consistent (max 0.5s staleness)
"""

import os
from typing import Dict, List, Optional
from uuid import UUID

import anyio

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.ticketing.app.interface import ISeatStateQueryHandler


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

    Cache Strategy:
    - Singleton with shared in-memory cache
    - Background polling refreshes all event stats every 0.5s
    """

    def __init__(self):
        self._cache: Dict[UUID, Dict[str, Dict]] = {}  # {event_id: {section_id: stats}}

    @staticmethod
    def _calculate_seat_index(row: int, seat_num: int, seats_per_row: int) -> int:
        """計算座位在 Bitfield 中的 index"""
        return (row - 1) * seats_per_row + (seat_num - 1)

    @Logger.io
    async def _get_section_config(self, event_id: UUID, section_id: str) -> Dict:
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
    async def get_seat_states(self, seat_ids: List[str], event_id: UUID) -> Dict[str, Dict]:
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
    async def get_seat_price(self, seat_id: str, event_id: UUID) -> Optional[int]:
        """獲取座位價格"""
        seat_states = await self.get_seat_states([seat_id], event_id)
        seat_state = seat_states.get(seat_id)
        return seat_state.get('price') if seat_state else None

    # @Logger.io
    async def list_all_subsection_status(self, event_id: UUID) -> Dict[str, Dict]:
        """獲取活動所有 subsection 的統計資訊"""

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
                    'event_id': stats.get('event_id', ''),  # Keep as string UUID
                    'available': int(stats.get('available', 0)),
                    'reserved': int(stats.get('reserved', 0)),
                    'sold': int(stats.get('sold', 0)),
                    'total': int(stats.get('total', 0)),
                    'updated_at': int(stats.get('updated_at', 0)),
                }

        return all_stats

    async def _get_all_event_ids(self) -> list[UUID]:
        """Get all event IDs from Kvrocks"""
        from uuid import UUID

        client = kvrocks_client.get_client()
        keys = await client.keys(_make_key('event_sections:*'))  # type: ignore
        event_ids = []
        for key in keys:
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            event_id_str = key_str.replace(_KEY_PREFIX, '').replace('event_sections:', '')
            try:
                event_ids.append(UUID(event_id_str))
            except (ValueError, AttributeError):
                pass  # Skip invalid UUIDs
        return event_ids

    async def _refresh_all_caches(self) -> None:
        """Refresh cache for all events (no lock, eventual consistency)"""
        try:
            event_ids = await self._get_all_event_ids()

            for event_id in event_ids:
                stats = await self.list_all_subsection_status(event_id)
                self._cache[event_id] = stats

            sum(len(sections) for sections in self._cache.values())
            # Logger.base.debug(
            #     f'💾 [CACHE] Refreshed {len(event_ids)} events, {total_sections} sections'
            # )
        except Exception as e:
            Logger.base.error(f'❌ [CACHE] Refresh failed: {e}')

    async def start_polling(self) -> None:
        """Start background polling for all events (0.5s interval)"""
        # Initialize Kvrocks for this event loop (must succeed, otherwise polling is useless)
        await kvrocks_client.initialize()
        Logger.base.info('🔄 [POLLING] Starting seat state cache polling (Kvrocks ready)')

        await self._refresh_all_caches()

        while True:
            await anyio.sleep(0.5)
            await self._refresh_all_caches()

    @Logger.io
    async def list_all_subsection_seats(
        self, event_id: UUID, section: str, subsection: int
    ) -> List[Dict]:
        """
        獲取指定 subsection 的所有座位（包括 available, reserved, sold）

        Performance optimization:
        - Uses GETRANGE to fetch entire bitfield in ONE Redis call (instead of 2N getbit calls)
        - Uses pipeline to batch fetch all row metadata
        - Reduces Redis calls from 2000+ to just 2-3 for a 20×50 section
        """
        Logger.base.info(
            f'📊 [QUERY] Listing all seats for event {event_id}, section {section}-{subsection}'
        )

        section_id = f'{section}-{subsection}'
        config = await self._get_section_config(event_id, section_id)
        total_rows = config['rows']
        seats_per_row = config['seats_per_row']
        total_seats = total_rows * seats_per_row

        # Get client from initialized pool (no await needed)
        client = kvrocks_client.get_client()
        bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')

        # OPTIMIZATION 1: Fetch entire bitfield in ONE call (instead of 2N getbit calls)
        # Each seat uses 2 bits, so we need (total_seats * 2) bits = (total_seats / 4) bytes
        bytes_needed = (total_seats * 2 + 7) // 8  # Round up to nearest byte
        bitfield_bytes = await client.getrange(bf_key, 0, bytes_needed - 1)  # type: ignore

        # Handle case where bitfield doesn't exist yet (returns None or empty bytes)
        if not bitfield_bytes:
            bitfield_bytes = b''  # Empty bytes, all seats will be 'available'

        # OPTIMIZATION 2: Batch fetch all row metadata with pipeline
        pipe = client.pipeline()
        for row in range(1, total_rows + 1):
            meta_key = _make_key(f'seat_meta:{event_id}:{section_id}:{row}')
            pipe.hgetall(meta_key)
        all_prices = await pipe.execute()

        # Build seat list from bitfield bytes
        all_seats = []
        for row in range(1, total_rows + 1):
            # Get price metadata for this row (from batched results)
            prices = all_prices[row - 1] or {}

            for seat_num in range(1, seats_per_row + 1):
                seat_index = self._calculate_seat_index(row, seat_num, seats_per_row)
                bit_offset = seat_index * 2

                # Extract 2 bits from bitfield_bytes
                byte_index = bit_offset // 8
                bit_position = 7 - (bit_offset % 8)  # Redis stores bits MSB first

                if byte_index < len(bitfield_bytes):
                    byte_value = bitfield_bytes[byte_index]
                    # Extract bit0 and bit1
                    bit0 = (byte_value >> bit_position) & 1
                    bit1 = (byte_value >> (bit_position - 1)) & 1 if bit_position > 0 else 0
                    status_value = bit0 * 2 + bit1
                else:
                    # Seat not initialized yet, default to available (00)
                    status_value = 0

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

        Logger.base.info(
            f'✅ [QUERY] Retrieved {len(all_seats)} seats for section {section_id} '
            f'(optimized: 2 Redis calls instead of {total_seats * 2})'
        )
        return all_seats
