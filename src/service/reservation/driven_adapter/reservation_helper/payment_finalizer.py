"""
Payment Finalizer

Handles finalizing seat payment (RESERVED -> SOLD).
"""

import orjson
from src.service.reservation.driven_adapter.reservation_helper.key_str_generator import (
    make_event_state_key,
    make_seats_bf_key,
)

from src.platform.state.kvrocks_client import kvrocks_client


class PaymentFinalizer:
    """Executes seat payment finalization (RESERVED -> SOLD)"""

    @staticmethod
    def _calculate_seat_index(row: int, seat_num: int, cols: int) -> int:
        """Calculate seat index in Bitfield"""
        return (row - 1) * cols + (seat_num - 1)

    async def finalize_seat_payment(
        self,
        *,
        seat_position: str,
        event_id: int,
        section: str,
        subsection: int,
    ) -> bool:
        """
        Finalize payment (RESERVED -> SOLD).

        Fetches cols from Kvrocks event_state config.

        Args:
            seat_position: Seat position (format: "row-seat", e.g., "1-5")
            event_id: Event ID
            section: Section name (e.g., "A")
            subsection: Subsection number (e.g., 1)
        """
        parts = seat_position.split('-')
        if len(parts) != 2:
            return False

        row, seat_num = parts
        section_id = f'{section}-{subsection}'

        # Fetch config from Kvrocks
        client = kvrocks_client.get_client()
        event_state_key = make_event_state_key(event_id=event_id)
        json_path = f"$.sections['{section}'].subsections['{str(subsection)}'].cols"
        result = await client.execute_command('JSON.GET', event_state_key, json_path)

        if not result:
            return False

        cols = orjson.loads(result)[0]
        seat_index = self._calculate_seat_index(int(row), int(seat_num), cols)

        bf_key = make_seats_bf_key(event_id=event_id, section_id=section_id)
        offset = seat_index * 2

        # Set to SOLD (10)
        await client.execute_command('BITFIELD', bf_key, 'SET', 'u2', offset, 2)
        return True
