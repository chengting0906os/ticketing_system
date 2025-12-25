import contextlib
import time

import anyio
from anyio.abc import TaskGroup
import orjson
from redis.asyncio import Redis as AsyncRedis

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.ticketing.app.interface.i_seat_availability_query_handler import (
    ISeatAvailabilityQueryHandler,
)


class RealTimeEventStateSubscriber:
    """Subscribe to Redis Pub/Sub for real-time event_state updates"""

    def __init__(
        self,
        *,
        event_id: int,
        cache_handler: ISeatAvailabilityQueryHandler,
        throttle_interval: float = 0.5,  # 500ms minimum interval between cache updates
        reconnect_delay: float = 5.0,  # Delay before reconnecting after error
    ) -> None:
        self.event_id = event_id
        self.cache_handler = cache_handler
        self.channel = f'event_state_updates:{event_id}'
        self._throttle_interval = throttle_interval
        self._reconnect_delay = reconnect_delay
        self._last_update_time: float = 0.0  # For throttling only
        self._pubsub_client: AsyncRedis | None = None

    async def start(self, *, task_group: TaskGroup) -> None:
        """Start Redis Pub/Sub subscription"""
        task_group.start_soon(self._subscribe_loop)  # pyrefly: ignore[bad-argument-type]
        Logger.base.info(f'🔔 [Cache Subscriber] Started for event {self.event_id}')

    async def _subscribe_loop(self) -> None:
        """Main subscription loop with automatic reconnection"""
        while True:
            try:
                # Create dedicated pub/sub client
                if self._pubsub_client is None:
                    self._pubsub_client = await kvrocks_client.create_pubsub_client()

                pubsub = self._pubsub_client.pubsub()

                try:
                    await pubsub.subscribe(self.channel)
                    Logger.base.info(f'📡 [Cache Subscriber] Subscribed to {self.channel}')

                    async for message in pubsub.listen():
                        if message['type'] == 'message':
                            await self._handle_update(message['data'])
                finally:
                    await pubsub.unsubscribe(self.channel)
                    await pubsub.aclose()

            except Exception as e:
                Logger.base.error(f'❌ [Cache Subscriber] Error: {e}')

                # Clean up client on error
                if self._pubsub_client:
                    with contextlib.suppress(Exception):
                        await self._pubsub_client.aclose()
                    self._pubsub_client = None

                # Wait before reconnecting
                Logger.base.info(
                    f'🔄 [Cache Subscriber] Reconnecting in {self._reconnect_delay}s...'
                )
                await anyio.sleep(self._reconnect_delay)

    async def _handle_update(self, data: bytes) -> None:
        """Handle incoming event_state update with throttling"""
        try:
            payload = orjson.loads(data)
            event_id = payload['event_id']
            event_state = payload['event_state']

            # Throttle cache updates to reduce overhead
            current_time = time.time()
            time_since_last_update = current_time - self._last_update_time

            if time_since_last_update < self._throttle_interval:
                return

            # Update cache with timestamp for TTL check
            self.cache_handler._cache[event_id] = {
                'data': event_state,
                'timestamp': current_time,
            }
            self._last_update_time = current_time
        except Exception as e:
            Logger.base.warning(f'⚠️ [Cache Subscriber] Parse error: {e}')
