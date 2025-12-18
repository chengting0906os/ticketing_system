"""
Kvrocks Booking Event Broadcaster Implementation

Distributed pub/sub for booking status events using Kvrocks (Redis-compatible).
Allows SSE endpoints across multiple service instances to receive events.
"""

from collections.abc import AsyncGenerator
from typing import Any

import orjson
from redis.asyncio import Redis as AsyncRedis

from src.platform.logging.loguru_io import Logger


class BookingEventBroadcasterImpl:
    """
    Kvrocks pub/sub broadcaster for booking status events

    Architecture:
    - Kafka Consumer → Use Case → publish() → Kvrocks → SSE Endpoint
    - Channel: booking:status:{user_id}:{event_id}
    - Distributed: works across multiple service instances

    Usage:
        # Publisher (in use case)
        await broadcaster.publish(user_id=1, event_id=2, event_data={...})

        # Subscriber (in SSE endpoint)
        async for event in broadcaster.subscribe(user_id=1, event_id=2):
            yield event
    """

    def __init__(self, *, redis_client: AsyncRedis) -> None:
        self._redis = redis_client

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
        channel = self._channel_name(user_id=user_id, event_id=event_id)
        message = orjson.dumps(event_data)

        subscribers = await self._redis.publish(channel, message)
        Logger.base.info(f'📡 [KVROCKS] Published to {channel}: subscribers={subscribers}')
