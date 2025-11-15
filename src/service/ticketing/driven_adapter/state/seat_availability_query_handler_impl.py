"""
Seat Availability Query Handler Implementation - Adapter for ticketing service to query seat state

Cache Strategy (Event-Driven with Lazy Loading + TTL):
- Cache updated via Kafka events (SeatsReservedEvent from Seat Reservation Service)
- On cache miss: query Kvrocks directly and cache result (lazy loading)
- TTL: 0.5 seconds (500ms) - cache expires and re-queries Kvrocks for fresh data
- No periodic polling needed - real-time updates via events
- Eventually consistent (depends on Kafka delivery latency, typically <100ms)
"""

import os
import time
from typing import Dict, TypedDict

from opentelemetry import trace

from src.platform.exception.exceptions import NotFoundError
from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.ticketing.app.interface.i_seat_availability_query_handler import (
    ISeatAvailabilityQueryHandler,
)


class CacheEntry(TypedDict):
    data: Dict
    timestamp: float


# Key prefix for Kvrocks (matches seat_reservation service convention)
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', '')


def _make_key(key: str) -> str:
    """Add prefix to key for environment isolation"""
    return f'{_KEY_PREFIX}{key}'


class SeatAvailabilityQueryHandlerImpl(ISeatAvailabilityQueryHandler):
    """
    Seat Availability Query Handler - Event-driven cache with lazy loading + TTL

    Purpose:
    - Check seat availability BEFORE creating booking records
    - Fail fast when insufficient seats available
    - Reduce unnecessary DB INSERT operations for doomed bookings

    Cache Strategy (Event-Driven + Lazy Loading + TTL):
    - Cache updated via Kafka events (real-time push from Seat Reservation Service)
    - On cache miss: query Kvrocks directly and cache result (lazy loading)
    - TTL: 0.5 seconds - prevents stale data in high-concurrency scenarios
    - No periodic polling - dramatically reduces Kvrocks query load
    - Eventually consistent (Kafka delivery latency, typically <100ms)

    Trade-off:
    - First query per subsection may hit Kvrocks (lazy loading)
    - Cache expires after 0.5s to ensure data freshness
    - Cache updates in real-time via events (no polling delay)
    """

    def __init__(self, *, ttl_seconds: float = 0.5):
        """
        Initialize handler with TTL-based cache

        Args:
            ttl_seconds: Time-to-live for cache entries (default: 0.5 seconds)

                        Design rationale:
                        - Primary goal: Auto-clear cache after seed_data in dev/test environments
                        - Production: Acceptable eventual consistency (~1s delay is fine)
                        - Kafka events handle real-time updates in high-concurrency scenarios
                        - TTL is a safety net for edge cases (event loss, consumer lag, seed_data)
        """
        self.tracer = trace.get_tracer(__name__)
        self._cache: Dict[int, Dict[str, CacheEntry]] = {}  # {event_id: {section_id: entry}}
        # Short TTL for dev/test: prevents cache pollution after seed_data
        # Production: eventual consistency acceptable, Kafka events handle most updates
        self._ttl_seconds = ttl_seconds

    def update_cache(self, *, event_id: int, section_id: str, stats: Dict) -> None:
        """Update cache with stats from event (event-driven push)"""
        if event_id not in self._cache:
            self._cache[event_id] = {}

        data = {
            'section_id': section_id,
            'event_id': event_id,
            'available': int(stats.get('available', 0)),
            'reserved': int(stats.get('reserved', 0)),
            'sold': int(stats.get('sold', 0)),
            'total': int(stats.get('total', 0)),
        }

        self._cache[event_id][section_id] = CacheEntry(data=data, timestamp=time.time())

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

    def _is_expired(self, *, entry: CacheEntry) -> bool:
        """Check if cache entry is expired"""
        return time.time() - entry['timestamp'] > self._ttl_seconds

    async def check_subsection_availability(
        self, *, event_id: int, section: str, subsection: int, required_quantity: int
    ) -> bool:
        """Check if subsection has sufficient seats (event-driven cache with TTL)"""
        with self.tracer.start_as_current_span('cache.check_availability') as span:
            section_id = f'{section}-{subsection}'

            # Try cache first (event-driven updates with TTL)
            event_cache = self._cache.get(event_id)
            if event_cache:
                cache_entry = event_cache.get(section_id)
                if cache_entry and not self._is_expired(entry=cache_entry):
                    # Cache hit and not expired
                    stats = cache_entry['data']
                    available_count = stats['available']
                    has_enough = available_count >= required_quantity
                    span.set_attribute('cache_hit', True)
                    span.set_attribute('cache_expired', False)
                    span.set_attribute('available_count', available_count)
                    span.set_attribute('has_enough', has_enough)

                    if has_enough:
                        Logger.base.info(f'✅ [CACHE HIT] {available_count} >= {required_quantity}')
                    else:
                        Logger.base.warning(
                            f'❌ [CACHE HIT] {available_count} < {required_quantity}'
                        )

                    return has_enough
                elif cache_entry:
                    # Cache expired
                    Logger.base.debug(
                        f'⏰ [CACHE EXPIRED] TTL exceeded for {section_id}, re-querying Kvrocks'
                    )
                    span.set_attribute('cache_hit', True)
                    span.set_attribute('cache_expired', True)

            # Cache miss or expired: lazy load from Kvrocks and cache result
            if not event_cache or section_id not in event_cache:
                Logger.base.debug(f'💾 [CACHE MISS] Lazy loading from Kvrocks: {section_id}')
                span.set_attribute('cache_hit', False)
                span.set_attribute('cache_expired', False)

            stats = await self._fetch_subsection_stats(event_id=event_id, section_id=section_id)

            if not stats:
                Logger.base.warning(f'⚠️ [AVAILABILITY] Section {section_id} not found')
                raise NotFoundError(f'Section {section_id} not found')

            # Cache the result for next query (lazy loading with timestamp)
            if event_id not in self._cache:
                self._cache[event_id] = {}
            self._cache[event_id][section_id] = CacheEntry(data=stats, timestamp=time.time())

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
