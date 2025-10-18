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
    座位可用性查詢處理器實作

    職責：直接查詢 Kvrocks 獲取座位狀態統計
    不依賴 seat_reservation service 的實現類，保持服務邊界清晰

    Cache Strategy:
    - Uses async-lru with 0.5s TTL to reduce Kvrocks load
    - Automatically manages cache lifecycle and expiration
    """

    def __init__(self):
        self.tracer = trace.get_tracer(__name__)

    @alru_cache(maxsize=128, ttl=0.5)
    async def _get_available_count(self, event_id: int, section: str, subsection: int) -> int:
        """
        Query Kvrocks for available seat count (cached with 0.5s TTL)

        Cache key includes all parameters (event_id, section, subsection) to ensure
        different sections/subsections have separate cache entries.

        Args:
            event_id: Event ID
            section: Section name (e.g., "A")
            subsection: Subsection number (e.g., 1)

        Returns:
            Available seat count

        Raises:
            NotFoundError: If section not found
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

        return int(stats.get('available', 0))

    # @Logger.io
    async def check_subsection_availability(
        self, *, event_id: int, section: str, subsection: int, required_quantity: int
    ) -> bool:
        """
        檢查指定 subsection 是否有足夠的可用座位

        Uses async-lru cache (0.5s TTL) to reduce Kvrocks load on high-frequency queries
        """
        with self.tracer.start_as_current_span('kvrocks.check_availability') as span:
            try:
                # Query with automatic caching (0.5s TTL via @alru_cache)
                # Cache key: (event_id, section, subsection) - ensures different sections cached separately
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
