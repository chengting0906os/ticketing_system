"""
Booking Tracker Implementation using Kvrocks

Prevents duplicate bookings by tracking event_id:buyer_id:booking_id combinations.
Uses Redis SET NX (set if not exists) for atomic duplicate detection.
"""

from uuid import UUID

from redis.exceptions import RedisError

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.ticketing.app.interface.i_booking_tracker import IBookingTracker


class BookingTrackerImpl(IBookingTracker):
    """
    Kvrocks-based booking tracker for duplicate prevention

    Key format: booking:track:{event_id}:{buyer_id}
    Value: booking_id
    TTL: 86400 seconds (1 day)

    Architecture:
    - Uses SET NX for atomic check-and-set
    - TTL auto-expires tracking after 1 day
    - Supports compensating transactions via explicit removal
    """

    # 1 day in seconds
    TRACKING_TTL_SECONDS = 86400

    def __init__(self):
        """Initialize booking tracker - uses global kvrocks_client singleton"""
        pass

    def _build_tracking_key(self, *, event_id: UUID, buyer_id: UUID) -> str:
        return f'booking:track:{event_id}:{buyer_id}'

    async def track_booking(self, *, event_id: UUID, buyer_id: UUID, booking_id: UUID) -> bool:
        """
        Track booking in Kvrocks with 1 day TTL

        Uses SET NX (set if not exists) for atomic duplicate detection.
        If key already exists, it means buyer has a pending booking.

        Args:
            event_id: Event ID
            buyer_id: Buyer ID
            booking_id: Booking ID to track

        Returns:
            True if tracked successfully (no duplicate)
            False if duplicate booking detected (buyer already has pending booking)
        """
        key = self._build_tracking_key(event_id=event_id, buyer_id=buyer_id)

        try:
            client = kvrocks_client.get_client()

            # SET NX: Set if not exists (returns True if key was set, False if already exists)
            # EX: Set expiry in seconds
            was_set = await client.set(
                name=key, value=str(booking_id), nx=True, ex=self.TRACKING_TTL_SECONDS
            )

            if was_set:
                Logger.base.info(
                    f'✅ [BOOKING-TRACKER] Tracked booking {booking_id} '
                    f'for event {event_id}, buyer {buyer_id} (TTL: {self.TRACKING_TTL_SECONDS}s)'
                )
                return True
            else:
                # Key already exists - duplicate detected
                existing_booking_id = await client.get(key)
                Logger.base.warning(
                    f'⚠️ [BOOKING-TRACKER] Duplicate detected! Buyer {buyer_id} '
                    f'already has pending booking {existing_booking_id} for event {event_id}'
                )
                return False

        except (RedisError, RuntimeError) as e:
            Logger.base.error(f'❌ [BOOKING-TRACKER] Failed to track booking {booking_id}: {e}')
            # On error, fail safe: allow booking creation (don't block user)
            # Log error for monitoring but return True
            return True

    async def remove_booking_track(
        self, *, event_id: UUID, buyer_id: UUID, booking_id: UUID
    ) -> None:
        """
        Remove booking tracking (compensating action)

        Used when:
        - Event publishing fails after booking creation
        - Booking is canceled or completed

        Args:
            event_id: Event ID
            buyer_id: Buyer ID
            booking_id: Booking ID to remove
        """
        key = self._build_tracking_key(event_id=event_id, buyer_id=buyer_id)

        try:
            client = kvrocks_client.get_client()
            deleted_count = await client.delete(key)

            if deleted_count > 0:
                Logger.base.info(
                    f'🧹 [BOOKING-TRACKER] Removed tracking for booking {booking_id} '
                    f'(event {event_id}, buyer {buyer_id})'
                )
            else:
                Logger.base.debug(
                    f'🧹 [BOOKING-TRACKER] No tracking found to remove for booking {booking_id} '
                    f'(event {event_id}, buyer {buyer_id}) - may have expired'
                )

        except (RedisError, RuntimeError) as e:
            Logger.base.error(
                f'❌ [BOOKING-TRACKER] Failed to remove tracking for booking {booking_id}: {e}'
            )
            # Non-critical error: tracking will expire naturally after TTL
