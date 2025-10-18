"""
Seat Availability Query Handler Implementation

座位可用性查詢處理器實作 - Adapter for ticketing service to query seat state
"""

import os

from async_lru import alru_cache
from opentelemetry import trace

from src.platform.exception.exceptions import NotFoundError
from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.ticketing.app.interface.i_seat_availability_query_handler import (
    ISeatAvailabilityQueryHandler,
)


# Key prefix for Kvrocks (matches seat_reservation service convention)
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')


def _make_key(key: str) -> str:
    """Add prefix to key for environment isolation"""
    return f'{_KEY_PREFIX}{key}'


class SeatAvailabilityQueryHandlerImpl(ISeatAvailabilityQueryHandler):
    """
    Seat Availability Query Handler - Pre-booking validation to reduce DB writes

    Purpose:
    - Check seat availability BEFORE creating booking records
    - Fail fast when insufficient seats available
    - Reduce unnecessary DB INSERT operations for doomed bookings

    Cache Strategy (In-Memory):
    - Uses @alru_cache with 1.0s TTL per instance
    - Per-instance cache acceptable because:
      1. Pre-booking check tolerates 1s data staleness
      2. Read-heavy workload (many checks per actual booking)
      3. Dramatically reduces Kvrocks query load
      4. Prevents DB writes for obviously failed requests

    Trade-off:
    - Cache may be slightly stale (1s max)
    - But prevents thousands of failed INSERT attempts
    - Better to occasionally reject valid request than allow doomed ones
    """

    def __init__(self):
        self.tracer = trace.get_tracer(__name__)

    @alru_cache(maxsize=512, ttl=1.0)
    async def _get_available_count_cached(
        self, event_id: int, section: str, subsection: int
    ) -> int:
        """
        Query Kvrocks for available seat count (in-memory cached with 1.0s TTL)

        Note: This is per-instance cache. Each scaled instance has its own cache.
        """
        section_id = f'{section}-{subsection}'
        client = kvrocks_client.get_client()
        stats_key = _make_key(f'section_stats:{event_id}:{section_id}')
        stats = await client.hgetall(stats_key)  # type: ignore

        if not stats:
            Logger.base.warning(
                f'⚠️  [AVAILABILITY CHECK] Section {section_id} not found for event {event_id}'
            )
            raise NotFoundError(f'Section {section_id} not found')

        Logger.base.debug(
            f'🔍 [CACHE MISS] Fetched from Kvrocks: event={event_id}, '
            f'section={section}-{subsection}, available={stats.get("available", 0)}'
        )
        return int(stats.get('available', 0))

    async def _get_available_count(self, event_id: int, section: str, subsection: int) -> int:
        """
        Query available seat count with cache hit/miss logging

        Args:
            event_id: Event ID
            section: Section name (e.g., "A")
            subsection: Subsection number (e.g., 1)

        Returns:
            Available seat count

        Raises:
            NotFoundError: If section not found
        """
        # Check cache info before call
        cache_info_before = self._get_available_count_cached.cache_info()

        # Call cached function
        result = await self._get_available_count_cached(event_id, section, subsection)

        # Check cache info after call to detect hit/miss
        cache_info_after = self._get_available_count_cached.cache_info()

        if cache_info_after.hits > cache_info_before.hits:
            Logger.base.debug(
                f'💾 [CACHE HIT] event={event_id}, section={section}-{subsection}, '
                f'available={result} | hits={cache_info_after.hits}, '
                f'misses={cache_info_after.misses}'
            )

        return result

    # @Logger.io
    async def check_subsection_availability(
        self, *, event_id: int, section: str, subsection: int, required_quantity: int
    ) -> bool:
        """
        Pre-booking validation: Check if subsection has sufficient available seats

        This is a GUARD CHECK before creating booking records in DB.
        Purpose: Fail fast to avoid unnecessary DB INSERT for requests that will fail anyway.

        Why 1s cache is acceptable:
        - This is a pre-check, not the final reservation (which happens in seat_reservation service)
        - Even with stale cache:
          * False negative (reject valid request): Rare, user retries
          * False positive (allow doomed request): Will fail later in actual reservation
        - Prevents massive DB write load from obviously failed requests
        - Trade-off: Slightly stale data vs thousands of prevented failed INSERTs

        Args:
            event_id: Event ID
            section: Section name (e.g., "A")
            subsection: Subsection number (e.g., 1)
            required_quantity: Number of seats requested

        Returns:
            True if sufficient seats available (or cache says so), False otherwise
        """
        with self.tracer.start_as_current_span('kvrocks.check_availability') as span:
            try:
                # Query with in-memory caching (1.0s TTL via @alru_cache)
                # Note: Per-instance cache - each scaled instance has its own
                available_count = await self._get_available_count(event_id, section, subsection)
                has_enough = available_count >= required_quantity

                span.set_attribute('available_count', available_count)
                span.set_attribute('has_enough', has_enough)

                if has_enough:
                    Logger.base.info(
                        f'✅ [AVAILABILITY CHECK] Sufficient seats: {available_count} available, '
                        f'{required_quantity} required'
                    )
                else:
                    Logger.base.warning(
                        f'❌ [AVAILABILITY CHECK] Insufficient seats: {available_count} available, '
                        f'{required_quantity} required'
                    )

                return has_enough

            except NotFoundError:
                raise
            except Exception as e:
                Logger.base.error(f'❌ [AVAILABILITY CHECK] Error checking availability: {e}')
                raise
