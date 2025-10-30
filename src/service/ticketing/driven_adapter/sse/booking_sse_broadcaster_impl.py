"""
Booking SSE Broadcaster Implementation

Driven Adapter implementing ISSEBroadcaster interface.

Architecture:
- In-memory storage of booking_id → Queue mappings
- Event-driven: Use cases broadcast to this adapter
- Async-first: All operations are non-blocking

Limitations (MVP):
- Single-instance only (no cross-instance broadcasting)
- Connection state lost on service restart
- All connections stored in memory

Future improvements:
- Redis Pub/Sub for cross-instance broadcasting
- Connection recovery with event replay
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from src.platform.logging.loguru_io import Logger


class BookingSSEBroadcasterImpl:
    def __init__(self):
        self._connections: Dict[UUID, asyncio.Queue] = {}
        self._lock = asyncio.Lock()  # For thread-safe operations

    async def subscribe(self, *, booking_id: UUID) -> asyncio.Queue:
        async with self._lock:
            if booking_id in self._connections:
                Logger.base.debug(f'📡 [SSE] Existing subscription found for booking {booking_id}')
                return self._connections[booking_id]

            # Create new queue for this booking
            queue: asyncio.Queue = asyncio.Queue(maxsize=100)
            self._connections[booking_id] = queue

            Logger.base.info(
                f'📡 [SSE] New subscription created for booking {booking_id} '
                f'(total connections: {len(self._connections)})'
            )

            return queue

    async def unsubscribe(self, *, booking_id: UUID) -> None:
        async with self._lock:
            if booking_id in self._connections:
                # Get queue and signal it to close
                queue = self._connections.pop(booking_id)

                # Put a sentinel value to signal connection close
                try:
                    await asyncio.wait_for(queue.put({'event_type': '_close'}), timeout=1.0)
                except asyncio.TimeoutError:
                    pass  # Queue full or consumer slow, just remove it

                Logger.base.info(
                    f'📡 [SSE] Unsubscribed booking {booking_id} '
                    f'(remaining connections: {len(self._connections)})'
                )

    async def broadcast(self, *, booking_id: UUID, status_update: Dict[str, Any]) -> None:
        async with self._lock:
            queue = self._connections.get(booking_id)

        if not queue:
            Logger.base.debug(
                f'📡 [SSE] No subscribers for booking {booking_id}, broadcast skipped'
            )
            return

        # Add timestamp if not present
        if 'updated_at' not in status_update:
            status_update['updated_at'] = datetime.now(timezone.utc).isoformat()

        # Add booking_id if not present
        if 'booking_id' not in status_update:
            status_update['booking_id'] = str(booking_id)

        try:
            # Non-blocking put with timeout
            await asyncio.wait_for(queue.put(status_update), timeout=1.0)

            Logger.base.info(
                f'📤 [SSE] Broadcasted {status_update.get("event_type")} to booking {booking_id}'
            )
        except asyncio.TimeoutError:
            Logger.base.warning(
                f'⚠️ [SSE] Queue full for booking {booking_id}, '
                f'event {status_update.get("event_type")} dropped'
            )
        except Exception as e:
            Logger.base.error(f'❌ [SSE] Failed to broadcast to booking {booking_id}: {e}')


# Global singleton instance
sse_broadcaster = BookingSSEBroadcasterImpl()
