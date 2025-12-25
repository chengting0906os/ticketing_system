"""Seat Availability Query Handler - Event-driven cache via Redis PubSub"""

import time
from typing import Any, Dict, TypedDict

from opentelemetry import trace

from src.service.ticketing.app.interface.i_seat_availability_query_handler import (
    ISeatAvailabilityQueryHandler,
)


class CacheEntry(TypedDict):
    data: Dict[str, Any]
    timestamp: float


class SeatAvailabilityQueryHandlerImpl(ISeatAvailabilityQueryHandler):
    """
    Event-driven cache for seat availability

    Architecture:
    - RealTimeEventStateSubscriber handles PubSub subscription at startup
    - This handler checks cache (populated by subscriber)
    - TTL 10s: If cache expired, pass through (let reservation service handle it)
    """

    def __init__(self, *, ttl_seconds: float = 10.0) -> None:
        self.tracer = trace.get_tracer(__name__)
        self._cache: Dict[int, CacheEntry] = {}
        self._ttl_seconds = ttl_seconds

    def _is_expired(self, *, entry: CacheEntry) -> bool:
        return time.time() - entry['timestamp'] > self._ttl_seconds

    async def check_availability(
        self, *, event_id: int, section: str, subsection: int, required_quantity: int
    ) -> bool:
        """
        Check if subsection has sufficient seats (event-driven cache)

        Strategy:
        - No cache → pass through
        - Cache expired (>10s) → pass through
        - Has valid cache → check availability
        """
        with self.tracer.start_as_current_span('use_case.cache.check_availability') as span:
            cache_entry = self._cache.get(event_id)

            # No cache: pass through
            if not cache_entry:
                span.set_attribute('cache_hit', False)
                span.set_attribute('pass_through', True)
                return True

            # Cache expired: pass through
            if self._is_expired(entry=cache_entry):
                span.set_attribute('cache_hit', False)
                span.set_attribute('cache_expired', True)
                span.set_attribute('pass_through', True)
                return True

            span.set_attribute('cache_hit', True)

            # Has valid cache: check availability
            event_state = cache_entry['data']
            section_data = event_state.get('sections', {}).get(section, {})
            subsection_data = section_data.get('subsections', {}).get(str(subsection))

            if subsection_data:
                stats = subsection_data.get('stats', {})
                available_count = stats.get('available', 0)
                return available_count >= required_quantity

            # subsection_data is None: section/subsection doesn't exist
            return False
