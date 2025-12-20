"""
Kvrocks Pub/Sub Handler Implementation

Distributed pub/sub for events using Kvrocks (Redis-compatible).
Supports both user-specific booking updates and event-wide seat state broadcasts.

Throttle Pattern:
- schedule_stats_broadcast() is called on each write
- First call starts a 1s timer
- After 1s, queries latest stats and broadcasts
- Subsequent writes during the timer window are ignored
"""

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

import anyio
import orjson
from redis.asyncio import Redis as AsyncRedis

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.shared_kernel.app.interface.i_pubsub_handler import IPubSubHandler

if TYPE_CHECKING:
    from src.service.shared_kernel.driven_adapter.event_stats_query_repo_impl import (
        EventStatsQueryRepoImpl,
    )


class PubSubHandlerImpl(IPubSubHandler):
    """
    Kvrocks pub/sub handler for booking and event state updates

    Supports two channel patterns:
    - booking:status:{user_id}:{event_id} - User-specific booking status
    - event_state_updates:{event_id} - Event seat state for all viewers

    Uses throttle pattern for event stats broadcasts (query + broadcast every 1s).
    """

    def __init__(
        self,
        *,
        redis_client: AsyncRedis,
        event_stats_query_repo: 'EventStatsQueryRepoImpl | None' = None,
        throttle_interval: float = 1,
    ) -> None:
        self._redis = redis_client
        self._throttle_interval = throttle_interval
        self._pending_timers: set[int] = set()  # event_ids with active timers
        self._event_stats_query_repo = event_stats_query_repo

    @Logger.io
    async def schedule_stats_broadcast(self, *, event_id: int) -> None:
        """
        Schedule a throttled stats broadcast for the event.

        If no timer is running for this event, starts a 1s timer.
        After timer expires, queries latest stats from DB and broadcasts via Redis.
        """
        if event_id in self._pending_timers:
            # Timer already running, no need to start another
            return

        self._pending_timers.add(event_id)

        # Start timer task (fire and forget)
        async def delayed_query_and_broadcast() -> None:
            try:
                await anyio.sleep(self._throttle_interval)

                if self._event_stats_query_repo is None:
                    Logger.base.warning('⚠️ [Throttle] event_stats_query_repo not set')
                    return

                # Query latest stats from PostgreSQL
                stats = await self._event_stats_query_repo.get_event_stats(event_id)

                # Broadcast to Redis pub/sub
                await self.broadcast_event_state(event_id=event_id, event_state=stats)

            except Exception as e:
                Logger.base.warning(f'⚠️ [Throttle] Failed for event={event_id}: {e}')
            finally:
                self._pending_timers.discard(event_id)

        # Spawn fire-and-forget task (FastAPI runs on asyncio)
        asyncio.create_task(delayed_query_and_broadcast())

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
        # Create dedicated client with no timeout for pub/sub
        pubsub_client = await kvrocks_client.create_pubsub_client()
        pubsub = pubsub_client.pubsub()

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
            await pubsub_client.aclose()
            Logger.base.info(f'📡 [KVROCKS] Unsubscribed from channel: {channel}')

    @Logger.io
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

    @Logger.io
    async def broadcast_event_state(self, *, event_id: int, event_state: dict) -> None:
        """
        Broadcast event_state update to Redis Pub/Sub channel

        Channel format: event_state_updates:{event_id}
        Message format: {'event_id': int, 'event_state': dict, 'timestamp': float}
        """
        try:
            current_time = time.time()
            channel = f'event_state_updates:{event_id}'
            message = orjson.dumps(
                {'event_id': event_id, 'event_state': event_state, 'timestamp': current_time}
            )

            await self._redis.publish(channel, message)

            Logger.base.debug(f'📤 [Broadcaster] Published update for event={event_id}')

        except Exception as e:
            Logger.base.warning(f'⚠️ [Event State Broadcaster] Publish failed: {e}')

    async def subscribe_event_state(
        self,
        *,
        event_id: int,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Subscribe to event seat state updates for all viewers

        Args:
            event_id: Event ID

        Yields:
            Event state dictionaries as they are published
        """
        channel = f'event_state_updates:{event_id}'
        # Create dedicated client with no timeout for pub/sub
        pubsub_client = await kvrocks_client.create_pubsub_client()
        pubsub = pubsub_client.pubsub()

        try:
            await pubsub.subscribe(channel)
            Logger.base.info(f'📡 [KVROCKS] Subscribed to event state channel: {channel}')

            async for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        data = message['data']
                        if isinstance(data, bytes):
                            event_data = orjson.loads(data)
                        else:
                            event_data = orjson.loads(data.encode())
                        yield event_data
                    except orjson.JSONDecodeError as e:
                        Logger.base.error(f'❌ [KVROCKS] Failed to decode event state: {e}')
                        continue

        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            await pubsub_client.aclose()
            Logger.base.info(f'📡 [KVROCKS] Unsubscribed from event state channel: {channel}')
