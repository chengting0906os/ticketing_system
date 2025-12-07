"""
Booking Result Broadcaster Implementation

Publishes booking results via Redis Pub/Sub for cross-service SSE communication.
"""

import time

import orjson

from src.platform.logging.loguru_io import Logger
from src.platform.state import kvrocks_client
from src.service.reservation.app.interface.i_booking_result_broadcaster import (
    IBookingResultBroadcaster,
)


class BookingResultBroadcasterImpl(IBookingResultBroadcaster):
    """
    Broadcast booking results via Redis Pub/Sub

    Used by Reservation Service to notify Ticketing Service SSE endpoints
    about booking completion (success or failure).

    Channel format: booking_result:{buyer_id}:{event_id}
    """

    async def broadcast_booking_result(
        self,
        *,
        buyer_id: int,
        event_id: int,
        booking_id: str,
        status: str,
        tickets: list[dict],
        total_price: float | None = None,
        error_message: str | None = None,
    ) -> None:
        """
        Publish booking result to Redis Pub/Sub

        Args:
            buyer_id: Buyer user ID
            event_id: Event ID
            booking_id: Booking UUID string
            status: Booking status (PENDING_PAYMENT, FAILED, etc.)
            tickets: List of ticket details
            total_price: Total price (for success)
            error_message: Error message (for failure)
        """
        try:
            client = kvrocks_client.get_client()
            channel = f'booking_result:{buyer_id}:{event_id}'

            message = {
                'event_type': 'booking_result',
                'buyer_id': buyer_id,
                'event_id': event_id,
                'booking_id': booking_id,
                'status': status,
                'tickets': tickets,
                'timestamp': time.time(),
            }

            if total_price is not None:
                message['total_price'] = total_price

            if error_message is not None:
                message['error_message'] = error_message

            await client.publish(channel, orjson.dumps(message))

            Logger.base.info(
                f'📤 [BOOKING-RESULT] Published to {channel}: '
                f'booking_id={booking_id}, status={status}'
            )

        except Exception as e:
            # Log but don't raise - SSE is best-effort
            Logger.base.warning(f'⚠️ [BOOKING-RESULT] Publish failed: {e}')
