"""
Payment Finalizer

Handles finalizing seat payment (RESERVED -> SOLD).
"""

import orjson

from src.platform.state.kvrocks_client import KvrocksClient
from src.service.reservation.driven_adapter.reservation_helper.key_str_generator import (
    make_event_state_key,
    make_seats_bf_key,
)


class PaymentFinalizer:
    """Executes seat payment finalization (RESERVED -> SOLD)"""

    def __init__(self, *, kvrocks_client: KvrocksClient) -> None:
        self._kvrocks_client = kvrocks_client

    @staticmethod
    def _calculate_seat_index(row: int, seat_num: int, cols: int) -> int:
        """Calculate seat index in Bitfield"""
        return (row - 1) * cols + (seat_num - 1)

    async def finalize_seat_payment(self, *, seat_id: str, event_id: int) -> bool:
        """
        Finalize payment (RESERVED -> SOLD).

        Fetches cols from Kvrocks event_state config.
        """
        parts = seat_id.split('-')
        if len(parts) != 4:
            return False

        section, subsection, row, seat_num = parts
        section_id = f'{section}-{subsection}'

        # Fetch config from Kvrocks
        client = self._kvrocks_client.get_client()
        event_state_key = make_event_state_key(event_id=event_id)
        json_path = f"$.sections['{section}'].subsections['{subsection}'].cols"
        result = await client.execute_command('JSON.GET', event_state_key, json_path)

        if not result:
            return False

        cols = orjson.loads(result)[0]
        seat_index = self._calculate_seat_index(int(row), int(seat_num), cols)

        bf_key = make_seats_bf_key(event_id=event_id, zone_id=section_id)
        offset = seat_index * 2

        # Set to SOLD (10)
        await client.execute_command('BITFIELD', bf_key, 'SET', 'u2', offset, 2)
        return True
