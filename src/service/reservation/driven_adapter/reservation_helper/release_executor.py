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

    async def release_seats(
        self,
        *,
        seat_positions: List[str],
        event_id: int,
        section: str,
        subsection: int,
    ) -> Dict[str, bool]:
        """
        Release seats (RESERVED -> AVAILABLE). Fetches config from Kvrocks.

        Args:
            seat_positions: List of seat positions (format: "row-seat", e.g., "1-5")
            event_id: Event ID
            section: Section name (e.g., "A")
            subsection: Subsection number (e.g., 1)
        """
        client = kvrocks_client.get_client()
        results: Dict[str, bool] = {}

        section_id = f'{section}-{subsection}'

        # Fetch config once (all seats are in same section)
        event_state_key = make_event_state_key(event_id=event_id)
        json_path = f"$.sections['{section}'].subsections['{str(subsection)}'].cols"
        config_result = await client.execute_command('JSON.GET', event_state_key, json_path)

        if not config_result:
            # Return all as failed if config not found
            return {seat_pos: False for seat_pos in seat_positions}

        cols = orjson.loads(config_result)[0]
        bf_key = make_seats_bf_key(event_id=event_id, section_id=section_id)

        for seat_position in seat_positions:
            parts = seat_position.split('-')
            if len(parts) != 2:
                results[seat_position] = False
                continue

            row, seat_num = parts
            seat_index = self._calculate_seat_index(int(row), int(seat_num), cols)
            offset = seat_index * 2

            # Set to AVAILABLE (00)
            await client.execute_command('BITFIELD', bf_key, 'SET', 'u2', offset, 0)
            results[seat_position] = True

        return results
