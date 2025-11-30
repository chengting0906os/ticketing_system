"""Event State Broadcaster Implementation via Redis Pub/Sub"""

import time

import orjson
from src.service.reservation.app.interface.i_event_state_broadcaster import (
    IEventStateBroadcaster,
)

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client


class EventStateBroadcasterImpl(IEventStateBroadcaster):
    """Broadcast event_state updates via Redis Pub/Sub for real-time cache synchronization"""

    def __init__(self, *, throttle_interval: float = 0.5) -> None:
        """
        Initialize broadcaster with throttling

        Args:
            throttle_interval: Minimum interval between broadcasts (default: 0.5s)
        """
        self._throttle_interval = throttle_interval
        self._last_broadcast_time: dict[int, float] = {}  # event_id -> last_broadcast_time

    async def broadcast_event_state(self, *, event_id: int, event_state: dict) -> None:
        """
        Publish event_state update to Redis Pub/Sub channel with throttling

        Channel format: event_state_updates:{event_id}
        Message format: {'event_id': int, 'event_state': dict, 'timestamp': float}

        Note:
            - Throttled to prevent excessive broadcasts (default: 0.5s minimum interval)
            - Non-blocking operation
            - Failures are logged but don't raise exceptions
            - Used by API service's RealTimeEventStateSubscriber for cache updates
        """
        try:
            # Throttle broadcasts to reduce overhead
            current_time = time.time()
            last_broadcast = self._last_broadcast_time.get(event_id, 0.0)
            time_since_last_broadcast = current_time - last_broadcast

            if time_since_last_broadcast < self._throttle_interval:
                Logger.base.debug(
                    f'⏱️ [Broadcaster] Throttled broadcast for event={event_id} '
                    f'(last broadcast {time_since_last_broadcast:.3f}s ago)'
                )
                return

            # Broadcast event state
            client = kvrocks_client.get_client()
            channel = f'event_state_updates:{event_id}'
            message = orjson.dumps(
                {'event_id': event_id, 'event_state': event_state, 'timestamp': current_time}
            )

            await client.publish(channel, message)
            self._last_broadcast_time[event_id] = current_time

            Logger.base.debug(f'📤 [Broadcaster] Published update for event={event_id}')

        except Exception as e:
            # Silently fail if Pub/Sub fails (non-critical, cache has TTL fallback)
            Logger.base.warning(f'⚠️ [Event State Broadcaster] Publish failed: {e}')
