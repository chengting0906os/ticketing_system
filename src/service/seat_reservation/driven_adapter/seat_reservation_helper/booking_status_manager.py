"""
Booking Status Manager

Handles booking status checking and updates for idempotency control.
"""

from typing import Dict, Optional

import orjson

from src.platform.logging.loguru_io import Logger
from src.service.shared_kernel.app.interface.i_booking_metadata_handler import (
    IBookingMetadataHandler,
)


class BookingStatusManager:
    """
    Manage booking status for idempotency control

    Responsibilities:
    - Check booking status for idempotency
    - Update booking status (RESERVE_SUCCESS, RESERVE_FAILED)
    - Return cached results for already-processed bookings

    Status Flow (Kvrocks metadata):
    - PENDING_RESERVATION → RESERVE_SUCCESS (atomic via MULTI/EXEC)
    - PENDING_RESERVATION → RESERVE_FAILED (if reservation fails)

    Note: No PROCESSING state needed - MULTI/EXEC guarantees atomicity
    """

    def __init__(self, *, booking_metadata_handler: IBookingMetadataHandler):
        self.booking_metadata_handler = booking_metadata_handler

    @staticmethod
    def _error_result(error_message: str) -> Dict:
        """Create error result"""
        return {
            'success': False,
            'reserved_seats': None,
            'total_price': 0,
            'subsection_stats': {},
            'event_stats': {},
            'error_message': error_message,
        }

    async def check_booking_status(self, *, booking_id: str) -> Optional[Dict]:
        """
        Check booking status for idempotency

        Returns:
            - None: No metadata found or PENDING_RESERVATION status, proceed with reservation
            - Dict with success=True: Already RESERVE_SUCCESS, return cached result
            - Dict with success=False: Already RESERVE_FAILED, return error

        Note: No PROCESSING state handling needed - MULTI/EXEC guarantees atomicity.
              Either metadata exists with RESERVE_SUCCESS, or safe to retry.
        """
        metadata = await self.booking_metadata_handler.get_booking_metadata(booking_id=booking_id)

        if not metadata:
            # No metadata found - this shouldn't happen in normal flow
            # (Ticketing Service should create it first)
            Logger.base.warning(
                f'⚠️ [IDEMPOTENCY] No metadata found for booking {booking_id}, proceeding anyway'
            )
            return None

        status = metadata.get('status')

        if status == 'RESERVE_SUCCESS':
            # Already successfully reserved
            Logger.base.warning(
                f'⚠️ [IDEMPOTENCY] Booking {booking_id} already RESERVE_SUCCESS - returning cached result'
            )

            reserved_seats = orjson.loads(metadata.get('reserved_seats', '[]'))
            total_price = int(metadata.get('total_price', 0))
            subsection_stats = orjson.loads(metadata.get('subsection_stats', '{}'))
            event_stats = orjson.loads(metadata.get('event_stats', '{}'))

            return {
                'success': True,
                'reserved_seats': reserved_seats,
                'total_price': total_price,
                'subsection_stats': subsection_stats,
                'event_stats': event_stats,
                'error_message': None,
            }

        elif status == 'RESERVE_FAILED':
            # Already failed
            error_msg = metadata.get('error_message', 'Reservation previously failed')
            Logger.base.warning(
                f'⚠️ [IDEMPOTENCY] Booking {booking_id} already RESERVE_FAILED: {error_msg}'
            )
            return self._error_result(error_msg)

        elif status == 'PENDING_RESERVATION':
            # Initial state - proceed with reservation
            Logger.base.info(
                f'🔄 [IDEMPOTENCY] Booking {booking_id} status=PENDING_RESERVATION, proceeding with reservation'
            )
            return None

        else:
            # Unknown status - log warning but proceed anyway
            Logger.base.warning(
                f'⚠️ [IDEMPOTENCY] Unknown status {status} for booking {booking_id}, proceeding'
            )
            return None

    async def save_reservation_failure(self, *, booking_id: str, error_message: str) -> None:
        """Save failed reservation to metadata"""
        await self.booking_metadata_handler.update_booking_status(
            booking_id=booking_id, status='RESERVE_FAILED', error_message=error_message
        )
        Logger.base.warning(f'❌ [STATUS] Updated booking {booking_id} to RESERVE_FAILED')
