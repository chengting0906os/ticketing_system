"""
Atomic Release Executor

Handles atomic seat release with idempotency control via booking metadata.
"""

from typing import Dict, List

import orjson
from opentelemetry import trace

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.reservation.driven_adapter.state.reservation_helper.key_str_generator import (
    make_event_state_key,
    make_seats_bf_key,
)
from src.service.shared_kernel.app.interface.i_booking_metadata_handler import (
    IBookingMetadataHandler,
)


class AtomicReleaseExecutor:
    """
    Atomic Release Executor - Kvrocks seat release with idempotency

    Flow:
    1. Check booking metadata status (idempotency)
    2. If already RELEASE_SUCCESS, return cached result (no-op)
    3. If not, release seats in Kvrocks (atomic via pipeline)
    4. Update booking metadata to RELEASE_SUCCESS

    Status Flow (Kvrocks metadata):
    - RESERVE_SUCCESS → RELEASE_SUCCESS (after cancellation)

    Note: Uses MULTI/EXEC pipeline for atomicity
    """

    def __init__(self, *, booking_metadata_handler: IBookingMetadataHandler) -> None:
        self.booking_metadata_handler = booking_metadata_handler
        self.tracer = trace.get_tracer(__name__)

    @staticmethod
    def _calculate_seat_index(row: int, seat_num: int, cols: int) -> int:
        """Calculate seat index in Bitfield"""
        return (row - 1) * cols + (seat_num - 1)

    # ========== Split Methods for New Flow ==========

    async def execute_fetch_release_config(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
    ) -> Dict:
        """
        Fetch config (cols) from Kvrocks for release.

        Returns:
            Dict with keys:
                - success: bool
                - cols: int
                - error_message: Optional[str]
        """
        client = kvrocks_client.get_client()
        event_state_key = make_event_state_key(event_id=event_id)
        json_path = f"$.sections['{section}'].subsections['{str(subsection)}'].cols"

        config_result = await client.execute_command('JSON.GET', event_state_key, json_path)

        if not config_result:
            return {
                'success': False,
                'cols': 0,
                'error_message': f'Config not found for event {event_id}',
            }

        cols = orjson.loads(config_result)[0]
        return {
            'success': True,
            'cols': cols,
            'error_message': None,
        }

    async def execute_update_seat_map_release(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        booking_id: str,
        seats_to_release: List[tuple],
    ) -> Dict:
        """
        Update seat map in Kvrocks for release via Pipeline.

        Args:
            seats_to_release: List of (seat_position, seat_index) tuples

        Returns:
            Dict with keys:
                - success: bool
                - released_seats: List[str]
                - error_message: Optional[str]
        """
        section_id = f'{section}-{subsection}'
        bf_key = make_seats_bf_key(event_id=event_id, section_id=section_id)
        client = kvrocks_client.get_client()

        released_seats = []
        pipe = client.pipeline(transaction=True)

        for seat_position, seat_index in seats_to_release:
            pipe.execute_command('BITFIELD', bf_key, 'SET', 'u1', seat_index, 0)
            released_seats.append(seat_position)

        await pipe.execute()

        Logger.base.info(
            f'✅ [RELEASE] Released {len(released_seats)} seats for booking {booking_id}'
        )

        return {
            'success': True,
            'released_seats': released_seats,
            'error_message': None,
        }
