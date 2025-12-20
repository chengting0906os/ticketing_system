"""Pub/Sub Handler Interface (Port)

Provides pub/sub mechanism for distributing events via Kvrocks pub/sub.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any


class IPubSubHandler(ABC):
    """
    Interface for pub/sub via Kvrocks

    Supports two channel patterns:
    - booking:status:{user_id}:{event_id} - User-specific booking status
    - event_state_updates:{event_id} - Event seat state for all viewers
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
    async def publish_booking_update(
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

    @abstractmethod
    async def broadcast_event_state(self, *, event_id: int, event_state: dict) -> None:
        """
        Broadcast event_state update for real-time seat status

        Args:
            event_id: Event ID
            event_state: Complete event state (sections + stats)
        """
        pass
