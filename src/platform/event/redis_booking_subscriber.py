"""
Redis Pub/Sub Booking Status Subscriber

Cross-container subscriber for booking status events using Redis Pub/Sub.
Channel format: booking_status:{buyer_id}:{event_id}
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import orjson
from redis.asyncio.cluster import RedisCluster

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client


class RedisBookingSubscriber:
    """
    Redis Pub/Sub subscriber for booking status events.

    Used by SSE endpoint in Ticketing Service to receive updates from Reservation Service.
    Channel: booking_status:{buyer_id}:{event_id}
    """

    @asynccontextmanager
    async def subscribe(
        self,
        *,
        buyer_id: int | str,
        event_id: int,
    ) -> AsyncIterator[asyncio.Queue[dict]]:
        """
        Subscribe to Redis Pub/Sub channel for booking status updates.

        Args:
            buyer_id: Buyer ID (int or UUID string)
            event_id: Event ID

        Yields:
            AsyncIterator yielding event data dicts
        """
        channel = f'booking_status:{buyer_id}:{event_id}'
        queue: asyncio.Queue[dict] = asyncio.Queue()
        client = kvrocks_client.get_client()

        try:
            if isinstance(client, RedisCluster):
                # Cluster mode: use get_pubsub with a node
                node = client.get_random_node()
                pubsub = client.pubsub(node=node)
            else:
                # Standalone mode
                pubsub = client.pubsub()

            await pubsub.subscribe(channel)
            Logger.base.info(f'📡 [BookingSubscriber] Subscribed to {channel}')

            # Start background task to read messages
            async def reader():
                try:
                    async for message in pubsub.listen():
                        if message['type'] == 'message':
                            try:
                                data = orjson.loads(message['data'])
                                await queue.put(data)
                            except Exception as e:
                                Logger.base.warning(
                                    f'⚠️ [BookingSubscriber] Failed to parse message: {e}'
                                )
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    Logger.base.warning(f'⚠️ [BookingSubscriber] Reader error: {e}')

            task = asyncio.create_task(reader())

            yield queue

        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            Logger.base.info(f'🔌 [BookingSubscriber] Unsubscribed from {channel}')


# Global singleton
redis_booking_subscriber = RedisBookingSubscriber()
