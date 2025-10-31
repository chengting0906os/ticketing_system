"""
In-memory Event Broadcaster Implementation

Singleton broadcaster for distributing booking status events
from Kafka consumer use cases to SSE endpoints.
"""

import asyncio
from typing import Dict, List
from pydantic import UUID7 as UUID

from src.platform.logging.loguru_io import Logger


class InMemoryEventBroadcasterImpl:
    """
    In-memory pub/sub for booking status events

    Architecture:
    - Kafka Consumer → Use Case → broadcast() → SSE Endpoint
    - Each booking_id has a list of subscriber queues
    - Thread-safe (uses asyncio primitives)
    - Auto-cleanup empty subscriber lists

    Memory Management:
    - Queue max size: 10 events
    - Drop policy: Silently drop if queue full
    - Cleanup: Remove empty lists on unsubscribe
    """

    def __init__(self):
        # booking_id → list of subscriber queues
        self._subscribers: Dict[UUID, List[asyncio.Queue]] = {}

    async def subscribe(self, *, booking_id: UUID) -> asyncio.Queue[dict]:
        """
        Create and register a new subscriber queue

        Args:
            booking_id: Booking UUID to subscribe to

        Returns:
            asyncio.Queue for receiving events
        """
        # Create queue with max size to prevent memory leaks
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=10)

        # Register subscriber
        if booking_id not in self._subscribers:
            self._subscribers[booking_id] = []

        self._subscribers[booking_id].append(queue)

        Logger.base.debug(
            f'📡 [BROADCASTER] Subscribed to booking {booking_id} '
            f'(total subscribers: {len(self._subscribers[booking_id])})'
        )

        return queue

    async def broadcast(self, *, booking_id: UUID, event_data: dict) -> None:
        """
        Broadcast event to all subscribers of this booking

        Args:
            booking_id: Booking UUID
            event_data: Event dictionary to send

        Note:
            - Non-blocking: drops event if queue is full
            - Silently ignores if no subscribers exist
        """
        if booking_id not in self._subscribers:
            # No subscribers, silently ignore
            Logger.base.debug(f'📡 [BROADCASTER] No subscribers for booking {booking_id}')
            return

        subscribers = self._subscribers[booking_id]
        delivered = 0
        dropped = 0

        for queue in subscribers:
            try:
                # Non-blocking put (raises QueueFull if full)
                queue.put_nowait(event_data)
                delivered += 1
            except asyncio.QueueFull:
                # Drop event if queue is full (slow consumer)
                dropped += 1
                Logger.base.warning(
                    f'⚠️ [BROADCASTER] Queue full for booking {booking_id}, '
                    f'dropping event (type={event_data.get("event_type")})'
                )

        Logger.base.info(
            f'📡 [BROADCASTER] Broadcast to booking {booking_id}: '
            f'delivered={delivered}, dropped={dropped}'
        )

    async def unsubscribe(self, *, booking_id: UUID, queue: asyncio.Queue) -> None:
        """
        Remove subscriber and cleanup

        Args:
            booking_id: Booking UUID
            queue: Queue to remove

        Note:
            - Removes empty subscriber lists to prevent memory leaks
            - Safe to call with non-existent booking_id or queue
        """
        if booking_id not in self._subscribers:
            return

        try:
            self._subscribers[booking_id].remove(queue)
            Logger.base.debug(
                f'📡 [BROADCASTER] Unsubscribed from booking {booking_id} '
                f'(remaining: {len(self._subscribers[booking_id])})'
            )
        except ValueError:
            # Queue not in list, ignore
            pass

        # Cleanup empty subscriber lists
        if not self._subscribers[booking_id]:
            del self._subscribers[booking_id]
            Logger.base.debug(f'📡 [BROADCASTER] Cleaned up empty list for {booking_id}')
