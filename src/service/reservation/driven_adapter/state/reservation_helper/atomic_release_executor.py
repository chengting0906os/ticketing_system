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
    make_booking_key,
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

    async def check_release_status(self, *, booking_id: str) -> Dict | None:
        """
        Check booking status for release idempotency.

        Returns:
            - None: Not yet released, proceed with release
            - Dict with success=True: Already RELEASE_SUCCESS, return cached result
        """
        metadata = await self.booking_metadata_handler.get_booking_metadata(booking_id=booking_id)

        if not metadata:
            # No metadata found - proceed with release anyway
            Logger.base.warning(
                f'⚠️ [RELEASE-IDEMPOTENCY] No metadata found for booking {booking_id}, proceeding'
            )
            return None

        status = metadata.get('status')

        if status == 'RELEASE_SUCCESS':
            # Already released
            Logger.base.info(
                f'✅ [RELEASE-IDEMPOTENCY] Booking {booking_id} already RELEASE_SUCCESS - skipping'
            )
            released_seats = orjson.loads(metadata.get('released_seats', '[]'))
            return {
                'success': True,
                'already_released': True,
                'released_seats': released_seats,
            }

        # Any other status - proceed with release
        return None

    async def execute_atomic_release(
        self,
        *,
        booking_id: str,
        event_id: int,
        section: str,
        subsection: int,
        seat_positions: List[str],
    ) -> Dict[str, bool]:
        """
        Execute atomic seat release with idempotency control.

        Flow:
        1. Check if already released (idempotency)
        2. Release seats in Kvrocks (RESERVED → AVAILABLE)
        3. Update event stats
        4. Update booking metadata to RELEASE_SUCCESS

        Args:
            booking_id: Booking identifier for idempotency
            event_id: Event ID
            section: Section name (e.g., "A")
            subsection: Subsection number (e.g., 1)
            seat_positions: List of seat positions (format: "row-seat", e.g., "1-5")

        Returns:
            Dict mapping seat_position to success status
        """
        with self.tracer.start_as_current_span(
            'executor.atomic_release',
            attributes={
                'booking.id': booking_id,
                'event.id': event_id,
                'seat.count': len(seat_positions),
            },
        ):
            # ========== STEP 0: Idempotency check ==========
            existing = await self.check_release_status(booking_id=booking_id)
            if existing:
                # Already released - return all as success (idempotent)
                return {seat_pos: True for seat_pos in seat_positions}

            client = kvrocks_client.get_client()
            section_id = f'{section}-{subsection}'

            # ========== STEP 1: Fetch config ==========
            event_state_key = make_event_state_key(event_id=event_id)
            json_path = f"$.sections['{section}'].subsections['{str(subsection)}'].cols"
            config_result = await client.execute_command('JSON.GET', event_state_key, json_path)

            if not config_result:
                Logger.base.error(f'❌ [RELEASE] Config not found for event {event_id}')
                return {seat_pos: False for seat_pos in seat_positions}

            cols = orjson.loads(config_result)[0]
            bf_key = make_seats_bf_key(event_id=event_id, section_id=section_id)

            # ========== STEP 2: Prepare seat data ==========
            seats_to_release: List[tuple] = []
            for seat_position in seat_positions:
                parts = seat_position.split('-')
                if len(parts) != 2:
                    continue
                row, seat_num = int(parts[0]), int(parts[1])
                seat_index = self._calculate_seat_index(row, seat_num, cols)
                seats_to_release.append((seat_position, seat_index))

            if not seats_to_release:
                return {seat_pos: False for seat_pos in seat_positions}

            num_seats = len(seats_to_release)

            # ========== STEP 3: Execute atomic release via pipeline ==========
            pipe = client.pipeline(transaction=True)

            # Release each seat (RESERVED → AVAILABLE)
            for _seat_position, seat_index in seats_to_release:
                offset = seat_index * 2
                pipe.execute_command('BITFIELD', bf_key, 'SET', 'u2', offset, 0)  # 00 = AVAILABLE

            # Update JSON statistics
            pipe.execute_command(
                'JSON.NUMINCRBY', event_state_key, '$.event_stats.available', num_seats
            )
            pipe.execute_command(
                'JSON.NUMINCRBY', event_state_key, '$.event_stats.reserved', -num_seats
            )

            # Update booking metadata to RELEASE_SUCCESS
            booking_key = make_booking_key(booking_id=booking_id)
            pipe.hset(
                booking_key,
                mapping={
                    'status': 'RELEASE_SUCCESS',
                    'released_seats': orjson.dumps(seat_positions).decode(),
                },
            )

            # Execute pipeline
            await pipe.execute()

            Logger.base.info(f'✅ [RELEASE] Released {num_seats} seats for booking {booking_id}')

            return {seat_pos: True for seat_pos in seat_positions}
