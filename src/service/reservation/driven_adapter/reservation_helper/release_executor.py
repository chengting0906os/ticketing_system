"""
Release Executor

Handles releasing seats from RESERVED back to AVAILABLE.
"""

from typing import Dict, List

import orjson
from src.service.reservation.driven_adapter.reservation_helper.key_str_generator import (
    make_event_state_key,
    make_seats_bf_key,
)

from src.platform.state.kvrocks_client import kvrocks_client


class ReleaseExecutor:
    """Executes seat release operations (RESERVED -> AVAILABLE)"""

    @staticmethod
    def _calculate_seat_index(row: int, seat_num: int, cols: int) -> int:
        """Calculate seat index in Bitfield"""
        return (row - 1) * cols + (seat_num - 1)

    async def release_seats(self, *, seat_ids: List[str], event_id: int) -> Dict[str, bool]:
        """Release seats (RESERVED -> AVAILABLE). Fetches config from Kvrocks."""
        client = kvrocks_client.get_client()
        results: Dict[str, bool] = {}

        # Cache config per section to avoid repeated fetches
        config_cache: Dict[str, int] = {}  # section_id -> cols

        for seat_id in seat_ids:
            parts = seat_id.split('-')
            if len(parts) != 4:
                results[seat_id] = False
                continue

            section, subsection, row, seat_num = parts
            section_id = f'{section}-{subsection}'

            # Fetch config if not cached
            if section_id not in config_cache:
                event_state_key = make_event_state_key(event_id=event_id)
                json_path = f"$.sections['{section}'].subsections['{subsection}'].cols"
                result = await client.execute_command('JSON.GET', event_state_key, json_path)
                if result:
                    config_cache[section_id] = orjson.loads(result)[0]
                else:
                    results[seat_id] = False
                    continue

            cols = config_cache[section_id]
            seat_index = self._calculate_seat_index(int(row), int(seat_num), cols)
            bf_key = make_seats_bf_key(event_id=event_id, section_id=section_id)
            offset = seat_index * 2

            # Set to AVAILABLE (00)
            await client.execute_command('BITFIELD', bf_key, 'SET', 'u2', offset, 0)
            results[seat_id] = True

        return results
