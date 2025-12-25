"""
Booking Metadata Handler Implementation

Kvrocks-based implementation for managing booking metadata.
"""

from datetime import datetime, timezone
import os
from typing import Dict, Optional

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.shared_kernel.app.interface.i_booking_metadata_handler import (
    IBookingMetadataHandler,
)


# Get key prefix from environment for test isolation
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')


def _make_key(key: str) -> str:
    """Add prefix to key for test isolation in parallel testing"""
    return f'{_KEY_PREFIX}{key}'


class BookingMetadataHandlerImpl(IBookingMetadataHandler):
    """
    Kvrocks-based booking metadata handler.

    Storage Format:
        Key: booking:{booking_id}
        Type: Hash
        Fields:
            - booking_id: UUID7 string
            - buyer_id: int
            - event_id: int
            - section: str
            - subsection: int
            - quantity: int
            - seat_selection_mode: str ('manual' or 'best_available')
            - seat_positions: JSON array string
            - status: str (PENDING_RESERVATION, COMPLETED, FAILED)
            - created_at: ISO timestamp
            - updated_at: ISO timestamp
            - error_message: str (optional, for FAILED status)

    TTL: 1 hour (auto cleanup if not processed)
    """

    @Logger.io
    async def get_booking_metadata(self, *, booking_id: str) -> Optional[Dict]:
        """Get booking metadata from Kvrocks"""
        try:
            client = kvrocks_client.get_client()
            key = _make_key(f'booking:{booking_id}')

            metadata = await client.hgetall(key)  # type: ignore

            if not metadata:
                return None

            # Convert bytes to str if needed
            result = {
                k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
                for k, v in metadata.items()
            }

            return result

        except Exception as e:
            Logger.base.error(f'❌ [BOOKING-META] Failed to get metadata: {e}')
            raise

    @Logger.io
    async def update_booking_status(
        self, *, booking_id: str, status: str, error_message: str = ''
    ) -> None:
        """Update booking status in Kvrocks"""
        try:
            client = kvrocks_client.get_client()
            key = _make_key(f'booking:{booking_id}')
            now = datetime.now(timezone.utc).isoformat()

            updates = {'status': status, 'updated_at': now}

            if error_message:
                updates['error_message'] = error_message

            await client.hset(key, mapping=updates)  # type: ignore

            Logger.base.info(f'✅ [BOOKING-META] Updated booking {booking_id} status to {status}')

        except Exception as e:
            Logger.base.error(f'❌ [BOOKING-META] Failed to update status: {e}')
            raise
