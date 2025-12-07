"""
Booking Result Broadcaster Interface

Publishes booking results via Redis Pub/Sub for cross-service SSE communication.
"""

from typing import Protocol


class IBookingResultBroadcaster(Protocol):
    """
    Interface for broadcasting booking results via Redis Pub/Sub

    Flow:
    1. Reservation Service calls broadcast_booking_result() after processing
    2. Message published to Redis channel: booking_result:{buyer_id}:{event_id}
    3. Ticketing Service SSE endpoint subscribes and pushes to client

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
        Broadcast booking result to Redis Pub/Sub

        Args:
            buyer_id: Buyer user ID
            event_id: Event ID
            booking_id: Booking UUID string
            status: Booking status (PENDING_PAYMENT, FAILED, etc.)
            tickets: List of ticket details
            total_price: Total price (for success)
            error_message: Error message (for failure)
        """
        ...
