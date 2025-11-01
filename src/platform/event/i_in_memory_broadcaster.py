"""
In-memory Event Broadcaster Interface

Provides pub/sub mechanism for distributing booking status events
from Kafka consumers to SSE endpoints within the same process.
"""

from typing import Protocol

from anyio.streams.memory import MemoryObjectReceiveStream
from uuid_utils import UUID


class IInMemoryEventBroadcaster(Protocol):
    """
    Interface for in-memory event broadcasting

    Used to distribute booking status updates from use cases
    (triggered by Kafka consumers) to SSE endpoints in real-time.

    Uses anyio's MemoryObjectStream for better async support and type safety.
    """

    async def subscribe(self, *, booking_id: UUID) -> MemoryObjectReceiveStream[dict]:
        """
        Subscribe to booking status updates

        Args:
            booking_id: Booking UUID to subscribe to

        Returns:
            MemoryObjectReceiveStream that will receive event dictionaries
        """
        ...

    async def broadcast(self, *, booking_id: UUID, event_data: dict) -> None:
        """
        Broadcast event to all subscribers of this booking

        Args:
            booking_id: Booking UUID
            event_data: Event dictionary to broadcast

        Note:
            - Silently ignores if no subscribers exist
            - Drops event if subscriber stream is full (prevents blocking)
        """
        ...

    async def unsubscribe(
        self, *, booking_id: UUID, stream: MemoryObjectReceiveStream[dict]
    ) -> None:
        """
        Unsubscribe and cleanup

        Args:
            booking_id: Booking UUID
            stream: Receive stream to remove from subscribers

        Note:
            - Removes empty subscriber lists to prevent memory leaks
            - Safe to call with non-existent stream
        """
        ...
