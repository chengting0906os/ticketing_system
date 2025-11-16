"""Seat Availability Query Handler - Event-driven cache with TTL"""

import os
import time
from typing import Dict, TypedDict

from opentelemetry import trace
import orjson

from src.platform.exception.exceptions import NotFoundError
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.ticketing.app.interface.i_seat_availability_query_handler import (
    ISeatAvailabilityQueryHandler,
)


class CacheEntry(TypedDict):
    data: Dict
    timestamp: float


_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')


def _make_key(key: str) -> str:
    return f'{_KEY_PREFIX}{key}'


class SeatAvailabilityQueryHandlerImpl(ISeatAvailabilityQueryHandler):
    """
    Event-driven cache for seat availability
    - Redis Pub/Sub updates cache (real-time <10ms)
    - Lazy load from Kvrocks on cache miss
    - TTL: 1s
    """

    def __init__(self, *, ttl_seconds: float = 1.0):
        """Initialize with TTL (default: 1s)"""
        self.tracer = trace.get_tracer(__name__)
        self._cache: Dict[int, CacheEntry] = {}
        self._ttl_seconds = ttl_seconds

    async def _fetch_and_cache_event_state(self, *, event_id: int) -> None:
        """Fetch event_state from Kvrocks and cache it"""
        client = kvrocks_client.get_client()
        key = _make_key(f'event_state:{event_id}')

        # Try JSON.GET, fallback to GET
        try:
            result = await client.execute_command('JSON.GET', key, '$')
            if isinstance(result, list) and result:
                result = result[0]
            json_str = result
        except Exception:
            return

        if not json_str:
            return

        # Parse and cache
        event_state = orjson.loads(json_str)
        if isinstance(event_state, list) and event_state:
            event_state = event_state[0]

        self._cache[event_id] = {'data': event_state, 'timestamp': time.time()}

    def _is_expired(self, *, entry: CacheEntry) -> bool:
        return time.time() - entry['timestamp'] > self._ttl_seconds

    async def check_subsection_availability(
        self, *, event_id: int, section: str, subsection: int, required_quantity: int
    ) -> bool:
        """Check if subsection has sufficient seats (event-driven cache with TTL)"""
        with self.tracer.start_as_current_span('cache.check_availability') as span:
            section_id = f'{section}-{subsection}'

            # Check cache validity (must exist and not expired)
            cache_entry = self._cache.get(event_id)
            if cache_entry and not self._is_expired(entry=cache_entry):
                # Cache hit and valid
                span.set_attribute('cache_hit', True)
                event_state = cache_entry['data']
                subsection_data = (
                    event_state.get('sections', {})
                    .get(section, {})
                    .get('subsections', {})
                    .get(str(subsection))
                )

                if subsection_data:
                    stats = subsection_data.get('stats', {})
                    available_count = stats.get('available', 0)
                    return available_count >= required_quantity

            # Cache miss or expired: re-fetch entire event_state
            span.set_attribute('cache_hit', False)
            await self._fetch_and_cache_event_state(event_id=event_id)

            # Now get data from cache (same logic as cache hit)
            cache_entry = self._cache.get(event_id)
            if not cache_entry:
                raise NotFoundError(f'Event {event_id} not found')

            event_state = cache_entry['data']
            subsection_data = (
                event_state.get('sections', {})
                .get(section, {})
                .get('subsections', {})
                .get(str(subsection))
            )

            if not subsection_data:
                raise NotFoundError(f'Section {section_id} not found')

            stats = subsection_data.get('stats', {})
            available_count = stats.get('available', 0)
            return available_count >= required_quantity
