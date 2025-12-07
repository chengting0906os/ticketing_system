"""
Booking Metadata Handler Implementation

Kvrocks-based implementation for managing booking metadata.
"""

from datetime import datetime, timezone
import os
from typing import Any, Dict, List, Optional

from opentelemetry import trace
import orjson
from redis.exceptions import NoScriptError

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

    BOOKING_TTL = 3600  # 1 hour

    # Lua script for atomic idempotent HSET + EXPIRE
    # Returns 1 if newly created, 0 if already exists (idempotency protection)
    LUA_HSETNX_EXPIRE = """
    -- Check if key already exists (idempotency check)
    if redis.call('EXISTS', KEYS[1]) == 1 then
        return 0  -- Already exists, don't overwrite
    end
    -- Key doesn't exist, create it atomically
    redis.call('HSET', KEYS[1], unpack(ARGV, 1, #ARGV - 1))
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[#ARGV]))
    return 1  -- Newly created
    """

    def __init__(self) -> None:
        """Initialize tracer and register Lua scripts"""
        self.tracer = trace.get_tracer(__name__)
        self._hsetnx_expire_script: Any = None  # Lazy registration on first use

    async def save_booking_metadata(
        self,
        *,
        booking_id: str,
        buyer_id: int,
        event_id: int,
        section: str,
        subsection: int,
        quantity: int,
        seat_selection_mode: str,
        seat_positions: list[str],
    ) -> bool:
        """
        Save booking metadata to Kvrocks with TTL (idempotent).

        Returns:
            True if newly created, False if already exists (idempotency protection)
        """
        with self.tracer.start_as_current_span(
            'use_case.booking_meta.save',
            attributes={
                'booking.id': booking_id,
                'cache.system': 'kvrocks',
                'cache.operation': 'hsetnx_expire',
            },
        ):
            try:
                client = kvrocks_client.get_client()
                key = _make_key(f'booking:{booking_id}')
                now = datetime.now(timezone.utc).isoformat()

                # Store as Hash for partial updates and atomic operations
                metadata = {
                    'booking_id': booking_id,
                    'buyer_id': str(buyer_id),
                    'event_id': str(event_id),
                    'section': section,
                    'subsection': str(subsection),
                    'quantity': str(quantity),
                    'seat_selection_mode': seat_selection_mode,
                    'seat_positions': orjson.dumps(seat_positions).decode(),
                    'status': 'PENDING_RESERVATION',
                    'created_at': now,
                    'updated_at': now,
                }

                # Lazy register Lua script on first use
                if self._hsetnx_expire_script is None:
                    self._hsetnx_expire_script = client.register_script(self.LUA_HSETNX_EXPIRE)

                # Build args for Lua script: field1, value1, field2, value2, ..., TTL
                args: List[Any] = []
                for k, v in metadata.items():
                    args.append(k)
                    args.append(v)
                args.append(self.BOOKING_TTL)

                # Execute Lua script (atomic EXISTS check + HSET + EXPIRE)
                # Retry once on NoScriptError (happens after Kvrocks restart)
                try:
                    result = await self._hsetnx_expire_script(keys=[key], args=args)
                except NoScriptError:
                    Logger.base.warning('⚠️ [BOOKING-META] Script not found, re-registering...')
                    self._hsetnx_expire_script = client.register_script(self.LUA_HSETNX_EXPIRE)
                    result = await self._hsetnx_expire_script(keys=[key], args=args)

                is_new = result == 1
                if not is_new:
                    Logger.base.warning(
                        f'⚠️ [BOOKING-META] Booking {booking_id} already exists (idempotency protection)'
                    )

                return is_new

            except Exception as e:
                Logger.base.error(f'❌ [BOOKING-META] Failed to save metadata: {e}')
                # Record exception on span
                span = trace.get_current_span()
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

    @Logger.io
    async def get_booking_metadata(self, *, booking_id: str) -> Optional[Dict]:
        """Get booking metadata from Kvrocks"""
        try:
            client = kvrocks_client.get_client()
            key = _make_key(f'booking:{booking_id}')

            metadata = await client.hgetall(key)  # type: ignore

            if not metadata:
                Logger.base.warning(f'⚠️ [BOOKING-META] Metadata not found: {booking_id}')
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

    @Logger.io
    async def delete_booking_metadata(self, *, booking_id: str) -> None:
        """Delete booking metadata from Kvrocks"""
        try:
            client = kvrocks_client.get_client()
            key = _make_key(f'booking:{booking_id}')

            await client.delete(key)  # type: ignore

            Logger.base.info(f'🗑️ [BOOKING-META] Deleted metadata for booking {booking_id}')

        except Exception as e:
            Logger.base.error(f'❌ [BOOKING-META] Failed to delete metadata: {e}')
            raise
