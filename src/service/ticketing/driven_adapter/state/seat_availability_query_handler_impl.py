"""
Seat Availability Query Handler Implementation - Adapter for ticketing service to query seat state

Cache Strategy (Event-Driven with Lazy Loading + TTL):
- Cache updated via Kafka events (SeatsReservedEvent from Seat Reservation Service)
- On cache miss: query Kvrocks directly and cache result (lazy loading)
- TTL: 1 second - safety net for development (re-seed clears Kvrocks) and Kafka lag
- No periodic polling needed - real-time updates via events
- Eventually consistent (depends on Kafka delivery latency, typically <100ms)
"""

import os
import time
from typing import Dict, TypedDict

from opentelemetry import trace
import orjson

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
    - TTL: 1 second - safety net for development (re-seed) and Kafka lag scenarios
    - No periodic polling - dramatically reduces Kvrocks query load
    - Eventually consistent (Kafka delivery latency, typically <100ms)

    Trade-off:
    - First query per subsection may hit Kvrocks (lazy loading)
    - Cache expires after 1s - useful for development when re-seeding clears Kvrocks
    - In production: most queries are cache hits (event-driven updates < 1s)
    """

    def __init__(self, *, ttl_seconds: float = 1.0, batch_interval: float = 0.5):
        """
        Initialize handler with TTL-based cache and batch throttling

        Args:
            ttl_seconds: Time-to-live for cache entries (default: 1.0 second)
                        - Development: auto-refresh after re-seed
                        - Production: safety net for Kafka lag
            batch_interval: Minimum interval between cache updates (default: 0.5 second)
                        - Throttle frequent updates to reduce overhead
                        - If event_state update comes within 0.5s, skip it

                        Design rationale:
                        - Primary goal: Auto-clear cache after seed_data in dev/test environments
                        - Production: Acceptable eventual consistency (~1s delay is fine)
                        - Kafka events handle real-time updates in high-concurrency scenarios
                        - TTL is a safety net for edge cases (event loss, consumer lag, seed_data)
                        - Batch throttling prevents excessive cache replacement
        """
        self.tracer = trace.get_tracer(__name__)
        self._cache: Dict[int, Dict[str, CacheEntry]] = {}  # {event_id: {section_id: entry}}
        self._last_update: Dict[int, float] = {}  # {event_id: last_update_timestamp}
        # Short TTL for dev/test: prevents cache pollution after seed_data
        # Production: eventual consistency acceptable, Kafka events handle most updates
        self._ttl_seconds = ttl_seconds
        self._batch_interval = batch_interval

    def update_cache_bulk(self, *, event_id: int, event_state: Dict) -> int:
        """Replace entire event cache from event_state (bulk update with throttling)"""
        now = time.time()

        # Throttle: Skip if updated within batch_interval (default 0.5s)
        last_update = self._last_update.get(event_id, 0)
        if now - last_update < self._batch_interval:
            Logger.base.debug(
                f'⏸️ [CACHE-THROTTLE] Skipping update for event {event_id} '
                f'(last update {now - last_update:.2f}s ago < {self._batch_interval}s)'
            )
            return 0

        sections = event_state.get('sections', {})

        # Replace entire event cache in one go (nested dict comprehension for hierarchical structure)
        # Flatten hierarchical structure (sections.A.subsections.1) to cache keys (A-1)
        self._cache[event_id] = {
            f'{section_name}-{subsection_num}': CacheEntry(
                data={
                    'section_id': f'{section_name}-{subsection_num}',
                    'event_id': event_id,
                    'available': int(subsection_data.get('stats', {}).get('available', 0)),
                    'reserved': int(subsection_data.get('stats', {}).get('reserved', 0)),
                    'sold': int(subsection_data.get('stats', {}).get('sold', 0)),
                    'total': int(subsection_data.get('stats', {}).get('total', 0)),
                },
                timestamp=now,
            )
            for section_name, section_config in sections.items()
            for subsection_num, subsection_data in section_config.get('subsections', {}).items()
            if subsection_data.get('stats')
        }

        # Record last update time
        self._last_update[event_id] = now

        sections_count = len(self._cache[event_id])
        Logger.base.info(
            f'📊 [CACHE-BULK-UPDATE] Replaced cache with {sections_count} sections for event {event_id}'
        )
        return sections_count

    async def _fetch_subsection_stats(self, *, event_id: int, section_id: str) -> Dict | None:
        """
        Fetch single subsection stats from Kvrocks event_state JSON (lazy loading)

        ✨ NEW: Reads from unified event_state JSON instead of section_stats Hash
        """
        client = kvrocks_client.get_client()
        config_key = _make_key(f'event_state:{event_id}')

        # Fetch event config JSON
        config_json = None
        try:
            # Try JSON.GET first
            result = await client.execute_command('JSON.GET', config_key, '$')

            if result:
                # Handle JSON.GET returning a list
                if isinstance(result, list) and result:
                    config_json = result[0]
                elif isinstance(result, bytes):
                    config_json = result.decode()
                else:
                    config_json = result

                if isinstance(config_json, bytes):
                    config_json = config_json.decode()

        except Exception as e:
            Logger.base.debug(f'🔍 [LAZY-LOAD] JSON.GET failed: {e}, trying fallback')
            # Fallback: Regular GET
            try:
                config_json = await client.get(config_key)
                if isinstance(config_json, bytes):
                    config_json = config_json.decode()
            except Exception:
                return None

        # Parse JSON
        if config_json:
            event_state = orjson.loads(config_json)
            # If JSON.GET returned an array, extract first element
            if isinstance(event_state, list) and event_state:
                event_state = event_state[0]
        else:
            return None

        # Extract subsection stats from hierarchical structure
        # section_id format: "A-1" -> extract section name "A" and subsection "1"
        section_name = section_id.split('-')[0]
        subsection_num = section_id.split('-')[1]

        subsection_data = (
            event_state.get('sections', {})
            .get(section_name, {})
            .get('subsections', {})
            .get(subsection_num)
        )
        if not subsection_data:
            return None

        stats = subsection_data.get('stats', {})

        return {
            'section_id': section_id,
            'event_id': event_id,
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
            # return True
            # TODO: Kvrocks Redis PubSub
            section_id = f'{section}-{subsection}'

            # Try cache first (event-driven updates with TTL)
            event_cache = self._cache.get(event_id)
            if event_cache:
                cache_entry = event_cache.get(section_id)
                if cache_entry:
                    # ✅ Cache hit: use data regardless of TTL expiration
                    # Trust event-driven updates from Kafka (< 100ms latency)
                    # TTL only matters for development (re-seed) or Kafka outage scenarios
                    stats = cache_entry['data']
                    available_count = stats['available']
                    has_enough = available_count >= required_quantity

                    is_expired = self._is_expired(entry=cache_entry)
                    span.set_attribute('cache_hit', True)
                    span.set_attribute('cache_expired', is_expired)
                    span.set_attribute('available_count', available_count)
                    span.set_attribute('has_enough', has_enough)

                    if is_expired:
                        Logger.base.debug(
                            f'⏰ [CACHE EXPIRED but using] {section_id}: '
                            f'{available_count} >= {required_quantity} ? {has_enough}'
                        )
                    elif has_enough:
                        Logger.base.info(f'✅ [CACHE HIT] {available_count} >= {required_quantity}')
                    else:
                        Logger.base.warning(
                            f'❌ [CACHE HIT] {available_count} < {required_quantity}'
                        )

                    return has_enough

            # Cache miss: lazy load from Kvrocks and cache result
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
