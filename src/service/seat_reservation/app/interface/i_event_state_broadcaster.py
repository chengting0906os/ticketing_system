"""Event State Broadcaster Interface (Port)"""

from abc import ABC, abstractmethod


class IEventStateBroadcaster(ABC):
    """Interface for broadcasting event_state updates to real-time cache"""

    @abstractmethod
    async def broadcast_event_state(self, *, event_id: int, event_state: dict) -> None:
        """
        Broadcast event_state update for real-time cache synchronization

        Args:
            event_id: Event ID
            event_state: Complete event state (sections + stats)

        Note:
            - Used for cache invalidation/update
            - Should be non-blocking (fire-and-forget)
            - Failures should be logged but not raise exceptions
        """
        pass
