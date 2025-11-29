"""
Payment Finalizer

Handles finalizing seat payment (RESERVED -> SOLD).
"""

import orjson

from src.platform.state.kvrocks_client import kvrocks_client
from src.service.seat_reservation.driven_adapter.seat_reservation_helper.key_str_generator import (
    make_event_state_key,
    make_seats_bf_key,
)


class PaymentFinalizer:
    """Executes seat payment finalization (RESERVED -> SOLD)"""

    @staticmethod
    def _calculate_seat_index(row: int, seat_num: int, seats_per_row: int) -> int:
        """Calculate seat index in Bitfield"""
        return (row - 1) * seats_per_row + (seat_num - 1)

    async def finalize_seat_payment(self, *, seat_id: str, event_id: int) -> bool:
        """
        Finalize payment (RESERVED -> SOLD).

        Fetches seats_per_row from Kvrocks event_state config.
        """
        parts = seat_id.split('-')
        if len(parts) != 4:
            return False

        section, subsection, row, seat_num = parts
        section_id = f'{section}-{subsection}'

        # Fetch config from Kvrocks
        client = kvrocks_client.get_client()
        event_state_key = make_event_state_key(event_id=event_id)
        json_path = f"$.sections['{section}'].subsections['{subsection}'].seats_per_row"
        result = await client.execute_command('JSON.GET', event_state_key, json_path)

        if not result:
            return False

        seats_per_row = orjson.loads(result)[0]
        seat_index = self._calculate_seat_index(int(row), int(seat_num), seats_per_row)

        bf_key = make_seats_bf_key(event_id=event_id, section_id=section_id)
        offset = seat_index * 2

        # Set to SOLD (10)
        await client.execute_command('BITFIELD', bf_key, 'SET', 'u2', offset, 2)
        return True
