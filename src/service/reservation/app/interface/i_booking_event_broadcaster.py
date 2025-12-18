"""Booking Event Broadcaster Interface (Port)

Provides pub/sub mechanism for distributing booking status events
from use cases to SSE endpoints via Kvrocks pub/sub.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any


class IBookingEventBroadcaster(ABC):
    """
    Interface for booking event broadcasting via Kvrocks pub/sub

    Subscription key: (user_id, event_id) tuple
    - Allows user to monitor all their bookings for a specific event
    - Distributed across service instances via Kvrocks pub/sub
    """

    @abstractmethod
    def subscribe(
        self,
        *,
        user_id: int,
        event_id: int,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Subscribe to booking status updates for a user's bookings of an event

        Args:
            user_id: User ID (buyer)
            event_id: Event ID

        Yields:
            Event dictionaries as they are published
        """
        if False:
            yield {}

    @abstractmethod
    async def publish(
        self,
        *,
        user_id: int,
        event_id: int,
        event_data: dict,
    ) -> None:
        """
        Publish event to all subscribers of this user+event combination

        Args:
            user_id: User ID (buyer)
            event_id: Event ID
            event_data: Event dictionary to publish
        """
        pass
