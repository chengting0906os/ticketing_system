"""
In-memory Event Broadcaster Implementation

Singleton broadcaster for distributing booking status events
from Kafka consumer use cases to SSE endpoints.
"""

from typing import Dict, List

from anyio import WouldBlock, create_memory_object_stream
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from uuid_utils import UUID

from src.platform.logging.loguru_io import Logger


class InMemoryEventBroadcasterImpl:
    """
    In-memory pub/sub for booking status events

    Architecture:
    - Kafka Consumer → Use Case → broadcast() → SSE Endpoint
    - Each booking_id has a list of subscriber stream tuples
    - Thread-safe (uses anyio primitives)
    - Auto-cleanup empty subscriber lists

    Memory Management:
    - Stream max buffer: 10 events
    - Drop policy: Silently drop if stream full (send_nowait raises WouldBlock)
    - Cleanup: Remove empty lists on unsubscribe and close streams
    """

    def __init__(self):
        # booking_id → list of (send_stream, receive_stream) tuples
        self._subscribers: Dict[
            UUID, List[tuple[MemoryObjectSendStream[dict], MemoryObjectReceiveStream[dict]]]
        ] = {}

    async def subscribe(self, *, booking_id: UUID) -> MemoryObjectReceiveStream[dict]:
        """
        Create and register a new subscriber stream

        Args:
            booking_id: Booking UUID to subscribe to

        Returns:
            MemoryObjectReceiveStream for receiving events
        """
        # Create memory object stream with max buffer of 10 to prevent memory leaks
        send_stream, receive_stream = create_memory_object_stream[dict](max_buffer_size=10)

        # Register subscriber
        if booking_id not in self._subscribers:
            self._subscribers[booking_id] = []

        self._subscribers[booking_id].append((send_stream, receive_stream))

        Logger.base.debug(
            f'📡 [BROADCASTER] Subscribed to booking {booking_id} '
            f'(total subscribers: {len(self._subscribers[booking_id])})'
        )

        return receive_stream

    async def broadcast(self, *, booking_id: UUID, event_data: dict) -> None:
        """
        Broadcast event to all subscribers of this booking

        Args:
            booking_id: Booking UUID
            event_data: Event dictionary to send

        Note:
            - Non-blocking: drops event if stream buffer is full
            - Silently ignores if no subscribers exist
        """
        if booking_id not in self._subscribers:
            # No subscribers, silently ignore
            Logger.base.debug(f'📡 [BROADCASTER] No subscribers for booking {booking_id}')
            return

        subscribers = self._subscribers[booking_id]
        delivered = 0
        dropped = 0

        for send_stream, _ in subscribers:
            try:
                # Non-blocking send (raises WouldBlock if full)
                send_stream.send_nowait(event_data)
                delivered += 1
            except WouldBlock:
                # Drop event if stream buffer is full (slow consumer)
                dropped += 1
                Logger.base.warning(
                    f'⚠️ [BROADCASTER] Stream full for booking {booking_id}, '
                    f'dropping event (type={event_data.get("event_type")})'
                )

        Logger.base.info(
            f'📡 [BROADCASTER] Broadcast to booking {booking_id}: '
            f'delivered={delivered}, dropped={dropped}'
        )

    async def unsubscribe(
        self, *, booking_id: UUID, stream: MemoryObjectReceiveStream[dict]
    ) -> None:
        """
        Remove subscriber and cleanup

        Args:
            booking_id: Booking UUID
            stream: Receive stream to remove

        Note:
            - Removes empty subscriber lists to prevent memory leaks
            - Safe to call with non-existent booking_id or stream
        """
        if booking_id not in self._subscribers:
            return

        # Find and remove the stream tuple
        subscribers = self._subscribers[booking_id]
        for i, (send_stream, receive_stream) in enumerate(subscribers):
            if receive_stream is stream:
                # Close the streams
                await send_stream.aclose()
                await receive_stream.aclose()
                # Remove from list
                subscribers.pop(i)
                Logger.base.debug(
                    f'📡 [BROADCASTER] Unsubscribed from booking {booking_id} '
                    f'(remaining: {len(subscribers)})'
                )
                break

        # Cleanup empty subscriber lists
        if not self._subscribers[booking_id]:
            del self._subscribers[booking_id]
            Logger.base.debug(f'📡 [BROADCASTER] Cleaned up empty list for {booking_id}')
