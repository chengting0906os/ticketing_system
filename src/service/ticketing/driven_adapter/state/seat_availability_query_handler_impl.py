"""
Seat Availability Query Handler Implementation - Adapter for ticketing service to query seat state

Cache Strategy (Event-Driven with Lazy Loading):
- Cache updated via Kafka events (SeatsReservedEvent from Seat Reservation Service)
- On cache miss: query Kvrocks directly and cache result (lazy loading)
- No periodic polling needed - real-time updates via events
- Eventually consistent (depends on Kafka delivery latency, typically <100ms)
"""

import os
from typing import Dict

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
    Seat Availability Query Handler - Event-driven cache with lazy loading

    Purpose:
    - Check seat availability BEFORE creating booking records
    - Fail fast when insufficient seats available
    - Reduce unnecessary DB INSERT operations for doomed bookings

    Cache Strategy (Event-Driven + Lazy Loading):
    - Cache updated via Kafka events (real-time push from Seat Reservation Service)
    - On cache miss: query Kvrocks directly and cache result (lazy loading)
    - No periodic polling - dramatically reduces Kvrocks query load
    - Eventually consistent (Kafka delivery latency, typically <100ms)

    Trade-off:
    - First query per subsection may hit Kvrocks (lazy loading)
    - Subsequent queries use cached data
    - Cache updates in real-time via events (no polling delay)
    """

    def __init__(self):
        self.tracer = trace.get_tracer(__name__)
        self._cache: Dict[int, Dict[str, Dict]] = {}  # {event_id: {section_id: stats}}

    def update_cache(self, *, event_id: int, section_id: str, stats: Dict) -> None:
        """Update cache with stats from event (event-driven push)"""
        if event_id not in self._cache:
            self._cache[event_id] = {}

        self._cache[event_id][section_id] = {
            'section_id': section_id,
            'event_id': event_id,
            'available': int(stats.get('available', 0)),
            'reserved': int(stats.get('reserved', 0)),
            'sold': int(stats.get('sold', 0)),
            'total': int(stats.get('total', 0)),
        }

        Logger.base.debug(
            f'💾 [CACHE-PUSH] Updated {section_id}: available={stats.get("available")}'
        )

    async def _fetch_subsection_stats(self, *, event_id: int, section_id: str) -> Dict | None:
        """Fetch single subsection stats from Kvrocks (lazy loading)"""
        client = kvrocks_client.get_client()
        stats_key = _make_key(f'section_stats:{event_id}:{section_id}')
        stats = await client.hgetall(stats_key)  # type: ignore

        if not stats:
            return None

        return {
            'section_id': stats.get('section_id'),
            'event_id': int(stats.get('event_id', 0)),
            'available': int(stats.get('available', 0)),
            'reserved': int(stats.get('reserved', 0)),
            'sold': int(stats.get('sold', 0)),
            'total': int(stats.get('total', 0)),
        }

    async def check_subsection_availability(
        self, *, event_id: int, section: str, subsection: int, required_quantity: int
    ) -> bool:
        """Check if subsection has sufficient seats (event-driven cache with lazy loading)"""
        with self.tracer.start_as_current_span('cache.check_availability') as span:
            section_id = f'{section}-{subsection}'

            # Try cache first (event-driven updates)
            event_cache = self._cache.get(event_id)
            if event_cache:
                stats = event_cache.get(section_id)
                if stats:
                    available_count = stats['available']
                    has_enough = available_count >= required_quantity
                    span.set_attribute('cache_hit', True)
                    span.set_attribute('available_count', available_count)
                    span.set_attribute('has_enough', has_enough)

                    if has_enough:
                        Logger.base.info(f'✅ [CACHE HIT] {available_count} >= {required_quantity}')
                    else:
                        Logger.base.warning(
                            f'❌ [CACHE HIT] {available_count} < {required_quantity}'
                        )

                    return has_enough

            # Cache miss: lazy load from Kvrocks and cache result
            Logger.base.debug(f'💾 [CACHE MISS] Lazy loading from Kvrocks: {section_id}')
            span.set_attribute('cache_hit', False)

            stats = await self._fetch_subsection_stats(event_id=event_id, section_id=section_id)

            if not stats:
                Logger.base.warning(f'⚠️ [AVAILABILITY] Section {section_id} not found')
                raise NotFoundError(f'Section {section_id} not found')

            # Cache the result for next query (lazy loading)
            if event_id not in self._cache:
                self._cache[event_id] = {}
            self._cache[event_id][section_id] = stats

            available_count = stats['available']
            has_enough = available_count >= required_quantity

            span.set_attribute('available_count', available_count)
            span.set_attribute('has_enough', has_enough)

            if has_enough:
                Logger.base.info(
                    f'✅ [LAZY-LOAD] {section_id}: {available_count} >= {required_quantity}'
                )
            else:
                Logger.base.warning(
                    f'❌ [LAZY-LOAD] {section_id}: {available_count} < {required_quantity}'
                )

            return has_enough
