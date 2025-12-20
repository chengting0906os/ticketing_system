"""
Kvrocks Pub/Sub Handler Implementation

Distributed pub/sub for events using Kvrocks (Redis-compatible).
Supports both user-specific booking updates and event-wide seat state broadcasts.
"""

import time
from collections.abc import AsyncGenerator
from typing import Any

import orjson
from redis.asyncio import Redis as AsyncRedis

from src.platform.logging.loguru_io import Logger


class PubSubHandlerImpl:
    """
    Kvrocks pub/sub handler for booking and event state updates

    Supports two channel patterns:
    - booking:status:{user_id}:{event_id} - User-specific booking status
    - event_state_updates:{event_id} - Event seat state for all viewers
    """

    def __init__(self, *, redis_client: AsyncRedis, throttle_interval: float = 0.5) -> None:
        self._redis = redis_client
        self._throttle_interval = throttle_interval
        self._last_broadcast_time: dict[int, float] = {}

    def _channel_name(self, *, user_id: int, event_id: int) -> str:
        """Generate channel name for user+event combination"""
        return f'booking:status:{user_id}:{event_id}'

    async def subscribe(
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
        channel = self._channel_name(user_id=user_id, event_id=event_id)
        pubsub = self._redis.pubsub()

        try:
            await pubsub.subscribe(channel)
            Logger.base.info(f'📡 [KVROCKS] Subscribed to channel: {channel}')

            async for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        data = message['data']
                        # Handle both bytes and string responses
                        if isinstance(data, bytes):
                            event_data = orjson.loads(data)
                        else:
                            event_data = orjson.loads(data.encode())
                        yield event_data
                    except orjson.JSONDecodeError as e:
                        Logger.base.error(f'❌ [KVROCKS] Failed to decode message: {e}')
                        continue

        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            Logger.base.info(f'📡 [KVROCKS] Unsubscribed from channel: {channel}')

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
        channel = self._channel_name(user_id=user_id, event_id=event_id)
        message = orjson.dumps(event_data)

        subscribers = await self._redis.publish(channel, message)
        Logger.base.info(f'📡 [KVROCKS] Published to {channel}: subscribers={subscribers}')

    async def broadcast_event_state(self, *, event_id: int, event_state: dict) -> None:
        """
        Broadcast event_state update to Redis Pub/Sub channel with throttling

        Channel format: event_state_updates:{event_id}
        Message format: {'event_id': int, 'event_state': dict, 'timestamp': float}
        """
        try:
            current_time = time.time()
            last_broadcast = self._last_broadcast_time.get(event_id, 0.0)

            if current_time - last_broadcast < self._throttle_interval:
                return

            channel = f'event_state_updates:{event_id}'
            message = orjson.dumps(
                {'event_id': event_id, 'event_state': event_state, 'timestamp': current_time}
            )

            await self._redis.publish(channel, message)
            self._last_broadcast_time[event_id] = current_time

            Logger.base.debug(f'📤 [Broadcaster] Published update for event={event_id}')

        except Exception as e:
            Logger.base.warning(f'⚠️ [Event State Broadcaster] Publish failed: {e}')
