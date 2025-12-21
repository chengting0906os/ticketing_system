"""
Seat State Query Handler Implementation

Seat State Query Handler Implementation - CQRS Query Side

Cache Strategy (Polling-based):
- Background task polls Kvrocks every 0.5s to refresh all seat stats
- Query methods can optionally read from in-memory cache
- Eventually consistent (max 0.5s staleness)
"""

import os
from typing import Dict, List, Optional

import orjson

from src.platform.exception.exceptions import NotFoundError
from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.shared_kernel.app.interface import ISeatStateQueryHandler


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
    def __init__(self) -> None:
        self._cache: Dict[int, Dict[str, Dict]] = {}  # {event_id: {section_id: stats}}

    @staticmethod
    def _calculate_seat_index(row: int, seat_num: int, cols: int) -> int:
        """Calculate the seat index in the Bitfield"""
        return (row - 1) * cols + (seat_num - 1)

    @Logger.io
    async def _get_section_config(self, event_id: int, section_id: str) -> Dict:
        """Get section configuration from event config JSON"""

        # Get client from initialized pool (no await needed)
        client = kvrocks_client.get_client()
        config_key = _make_key(f'event_state:{event_id}')

        # Fetch event config JSON
        try:
            # JSON.GET with $ returns: '[{"event_stats":{...},"sections":{...}}]'
            result = await client.execute_command('JSON.GET', config_key, '$')
            Logger.base.debug(f'🔍 [QUERY-READ] JSON.GET succeeded for {config_key}')

            if not result:
                Logger.base.error(f'❌ [QUERY-READ] No event config found for event_id={event_id}')
                event_state = {}
            else:
                # Parse JSON string array and extract first element
                event_state_list = orjson.loads(result)
                event_state = event_state_list[0]

        except Exception as e:
            Logger.base.error(f'❌ [QUERY-READ] Failed to fetch event config: {e}')
            event_state = {}

        # Debug: Log what we're reading
        Logger.base.info(
            f'🔍 [QUERY-READ] Event {event_id} sections in JSON: {list(event_state.get("sections", {}).keys())}'
        )
        Logger.base.info(f'🔍 [QUERY-READ] Looking for section_id: {section_id}')
        Logger.base.info(f'🔍 [QUERY-READ] Config key used: {config_key}')

        # Navigate hierarchical structure to get subsection config and section price
        # section_id format: "A-1" -> section "A", subsection "1"
        section_name = section_id.split('-')[0]
        subsection_num = section_id.split('-')[1]

        section_config = event_state.get('sections', {}).get(section_name, {})
        if not section_config:
            Logger.base.error(
                f'❌ [QUERY-READ] Section not found! Available sections: {list(event_state.get("sections", {}).keys())}, '
                f'Requested: {section_name} (from {section_id})'
            )
            raise NotFoundError('Event not found')

        subsection_config = section_config.get('subsections', {}).get(subsection_num, {})
        if not subsection_config:
            Logger.base.error(
                f'❌ [QUERY-READ] Subsection not found! Available subsections: {list(section_config.get("subsections", {}).keys())}, '
                f'Requested: {subsection_num} (from {section_id})'
            )
            raise NotFoundError('Event not found')

        return {
            'rows': int(subsection_config['rows']),
            'cols': int(subsection_config['cols']),
            'price': int(section_config['price']),  # Price from section level
        }

    @Logger.io
    async def get_seat_states(self, seat_ids: List[str], event_id: int) -> Dict[str, Dict]:
        """Get the states of specified seats"""
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
                # Get section config (includes price)
                config = await self._get_section_config(event_id, section_id)
                cols = config['cols']
                section_price = config['price']  # Price from JSON
                seat_index = self._calculate_seat_index(int(row), int(seat_num), cols)

                bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')
                offset = seat_index * 2

                # Read status from bitfield
                bit0 = await client.getbit(bf_key, offset)
                bit1 = await client.getbit(bf_key, offset + 1)
                status_value = bit0 * 2 + bit1

                # ✨ CHANGED: Price from section config JSON (not seat_meta Hash)

                seat_states[seat_id] = {
                    'seat_id': seat_id,
                    'event_id': event_id,
                    'status': BITFIELD_TO_STATUS.get(status_value, 'available'),
                    'price': section_price,  # Same price for all seats in section
                }

            except Exception as e:
                Logger.base.error(f'❌ [QUERY] Failed to get state for {seat_id}: {e}')
                continue

        Logger.base.info(f'✅ [QUERY] Retrieved {len(seat_states)} seat states')
        return seat_states

    @Logger.io
    async def get_seat_price(self, seat_id: str, event_id: int) -> Optional[int]:
        """Get seat price"""
        seat_states = await self.get_seat_states([seat_id], event_id)
        seat_state = seat_states.get(seat_id)
        return seat_state.get('price') if seat_state else None

    @Logger.io
    async def list_all_subsection_status(self, event_id: int) -> Dict[str, Dict]:
        """
        Get statistics for all subsections of an event

        ✨ NEW: Uses JSON.GET to fetch all section stats in one call
        (Previously: Pipeline with N HGETALL calls)
        """

        # Get client from initialized pool (no await needed)
        client = kvrocks_client.get_client()

        # ✨ Single JSON.GET to fetch all sections with stats
        config_key = _make_key(f'event_state:{event_id}')

        try:
            # JSON.GET with $ returns: '[{"event_stats":{...},"sections":{...}}]'
            result = await client.execute_command('JSON.GET', config_key, '$')

            if not result:
                return {}

            # Parse JSON string array and extract first element
            event_state_list = orjson.loads(result)
            event_state = event_state_list[0]

        except Exception as e:
            Logger.base.debug(f'🔍 [QUERY] Failed to fetch event config: {e}')
            return {}

        # Extract stats from hierarchical structure (sections -> subsections -> stats)
        all_stats = {}
        for section_name, section_config in event_state.get('sections', {}).items():
            # Navigate to subsections within each section
            for subsection_num, subsection_data in section_config.get('subsections', {}).items():
                # Build flat section_id key (e.g., "A-1")
                section_id = f'{section_name}-{subsection_num}'

                # Extract stats from subsection level
                stats = subsection_data.get('stats', {})
                all_stats[section_id] = {
                    'section_id': section_id,
                    'event_id': event_id,
                    'available': int(stats.get('available', 0)),
                    'reserved': int(stats.get('reserved', 0)),
                    'sold': int(stats.get('sold', 0)),
                    'total': int(stats.get('total', 0)),
                    'updated_at': int(stats.get('updated_at', 0)),
                }

        return all_stats

    @Logger.io
    async def list_all_subsection_seats(
        self, event_id: int, section: str, subsection: int
    ) -> List[Dict]:
        """
        Get all seats in a specified subsection (including available, reserved, sold)

        Performance optimization:
        - Uses GETRANGE to fetch entire bitfield in ONE Redis call (instead of 2N getbit calls)
        - Price from section config JSON (single price per section)
        - Reduces Redis calls to just 2 for a 20×50 section (config + bitfield)
        """
        Logger.base.info(
            f'📊 [QUERY] Listing all seats for event {event_id}, section {section}-{subsection}'
        )

        section_id = f'{section}-{subsection}'
        config = await self._get_section_config(event_id, section_id)
        total_rows = config['rows']
        cols = config['cols']
        section_price = config['price']  # Single price for entire section
        total_seats = total_rows * cols

        # Get client from initialized pool (no await needed)
        client = kvrocks_client.get_client()
        bf_key = _make_key(f'seats_bf:{event_id}:{section_id}')

        # OPTIMIZATION: Fetch entire bitfield in ONE call (instead of 2N getbit calls)
        # Each seat uses 2 bits, so we need (total_seats * 2) bits = (total_seats / 4) bytes
        # Note: Use GET instead of GETRANGE for Kvrocks bitmap type compatibility
        raw_data = await client.get(bf_key)  # type: ignore

        # Handle case where bitfield doesn't exist yet (returns None or empty bytes)
        if not raw_data:
            bitfield_bytes = b''  # Empty bytes, all seats will be 'available'
        elif isinstance(raw_data, bytes):
            bitfield_bytes = raw_data
        else:
            # Convert string to bytes if needed (Kvrocks may return string)
            bitfield_bytes = raw_data.encode('latin-1')

        # ✨ REMOVED: Pipeline to batch fetch row metadata (prices now in section config)

        # Build seat list from bitfield bytes
        all_seats = []
        for row in range(1, total_rows + 1):
            for seat_num in range(1, cols + 1):
                seat_index = self._calculate_seat_index(row, seat_num, cols)
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

                seat_position = f'{row}-{seat_num}'
                all_seats.append(
                    {
                        'section': section,
                        'subsection': subsection,
                        'row': row,
                        'seat_num': seat_num,
                        'price': section_price,  # Same price for all seats in section
                        'status': BITFIELD_TO_STATUS.get(status_value, 'available'),
                        'seat_position': seat_position,
                    }
                )

        Logger.base.info(
            f'✅ [QUERY] Retrieved {len(all_seats)} seats for section {section_id} '
            f'(optimized: 2 Redis calls instead of {total_seats * 2 + total_rows})'
        )
        return all_seats
