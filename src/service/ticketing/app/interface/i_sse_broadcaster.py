"""
SSE Broadcaster Interface

Abstraction for broadcasting real-time events to clients via Server-Sent Events.

Follows Dependency Inversion Principle:
- High-level modules (Use Cases) depend on this interface
- Low-level modules (Platform SSE Manager) implement this interface
"""

from typing import Any, Dict, Protocol
from uuid import UUID


class ISSEBroadcaster(Protocol):
    """Protocol for broadcasting status updates via SSE"""

    async def broadcast(self, *, booking_id: UUID, status_update: Dict[str, Any]) -> None:
        """
        Broadcast a status update to all subscribers of a booking

        Args:
            booking_id: The booking to broadcast to
            status_update: Event data to send (must include 'event_type' key)

        Note:
            Non-blocking operation - if no subscribers exist, the broadcast is skipped
        """
        ...
