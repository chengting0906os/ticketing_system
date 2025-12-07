"""
Redis Pub/Sub Booking Status Broadcaster

Cross-container broadcaster for booking status events using Redis Pub/Sub.
Channel format: booking_status:{buyer_id}:{event_id}
"""

import orjson
from redis.asyncio.cluster import RedisCluster

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client


class RedisBookingBroadcaster:
    """
    Redis Pub/Sub based broadcaster for booking status events.

    Works across containers (Reservation Service → Ticketing Service).
    Channel: booking_status:{buyer_id}:{event_id}
    """

    async def broadcast(
        self,
        *,
        buyer_id: int | str,
        event_id: int,
        event_data: dict,
    ) -> None:
        """
        Publish booking status event to Redis Pub/Sub channel.

        Args:
            buyer_id: Buyer ID (int or UUID string)
            event_id: Event ID
            event_data: Event payload (booking_id, status, tickets, etc.)
        """
        try:
            client = kvrocks_client.get_client()
            channel = f'booking_status:{buyer_id}:{event_id}'
            message = orjson.dumps(event_data)

            if isinstance(client, RedisCluster):
                # Cluster mode: PUBLISH needs a target node
                node = client.get_random_node()
                await client.execute_command('PUBLISH', channel, message, target_nodes=node)
            else:
                # Standalone mode
                await client.publish(channel, message)

            Logger.base.debug(
                f'📡 [BookingBroadcaster] Published to {channel}: '
                f'booking_id={event_data.get("booking_id")}, status={event_data.get("status")}'
            )
        except Exception as e:
            Logger.base.warning(f'⚠️ [BookingBroadcaster] Publish failed: {e}')


# Global singleton
redis_booking_broadcaster = RedisBookingBroadcaster()
