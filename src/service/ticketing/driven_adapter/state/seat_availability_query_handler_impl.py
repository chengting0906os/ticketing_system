"""
Seat Availability Query Handler Implementation

座位可用性查詢處理器實作 - Adapter for ticketing service to query seat state

Cache Strategy (Polling-based):
- Loads all seat stats into memory on startup
- Background task polls Kvrocks every 0.5s to refresh cache
- check_subsection_availability() reads from in-memory cache (no Kvrocks query)
- Eventually consistent (max 0.5s staleness)
"""

import os
from typing import Dict
from uuid import UUID

import anyio
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
    Seat Availability Query Handler - Pre-booking validation with polling-based cache

    Purpose:
    - Check seat availability BEFORE creating booking records
    - Fail fast when insufficient seats available
    - Reduce unnecessary DB INSERT operations for doomed bookings

    Cache Strategy (Polling-based):
    - Singleton instance with shared in-memory cache
    - Background task polls Kvrocks every 0.5s to refresh all seat stats
    - check_subsection_availability() reads from cache (no Kvrocks query)
    - Eventually consistent (max 0.5s staleness)

    Trade-off:
    - Cache may be slightly stale (0.5s max)
    - But dramatically reduces Kvrocks query load
    - Self-healing: Even if data is stale, it syncs within 0.5s
    """

    def __init__(self):
        self.tracer = trace.get_tracer(__name__)
        self._cache: Dict[UUID, Dict[str, Dict]] = {}  # {event_id: {section_id: stats}}

    async def _fetch_all_stats(self, event_id: UUID) -> Dict[str, Dict]:
        """Fetch all subsection stats from Kvrocks"""
        client = kvrocks_client.get_client()
        index_key = _make_key(f'event_sections:{event_id}')
        section_ids = await client.zrange(index_key, 0, -1)  # type: ignore

        if not section_ids:
            return {}

        pipe = client.pipeline()
        for section_id in section_ids:
            stats_key = _make_key(f'section_stats:{event_id}:{section_id}')
            pipe.hgetall(stats_key)

        results = await pipe.execute()

        all_stats = {}
        for section_id, stats in zip(section_ids, results, strict=False):
            if stats:
                all_stats[section_id] = {
                    'section_id': stats.get('section_id'),
                    'event_id': int(stats.get('event_id', 0)),
                    'available': int(stats.get('available', 0)),
                    'reserved': int(stats.get('reserved', 0)),
                    'sold': int(stats.get('sold', 0)),
                    'total': int(stats.get('total', 0)),
                }

        return all_stats

    async def _get_all_event_ids(self) -> list[UUID]:
        """Get all event IDs from Kvrocks"""
        client = kvrocks_client.get_client()
        # Scan for all event_sections:* keys
        keys = await client.keys(_make_key('event_sections:*'))  # type: ignore
        event_ids = []
        for key in keys:
            # Extract event_id from key like "event_sections:00000000-0000-0000-0000-000000000001"
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            event_id_str = key_str.replace(_KEY_PREFIX, '').replace('event_sections:', '')
            try:
                event_ids.append(UUID(event_id_str))
            except ValueError:
                # Skip invalid UUIDs
                continue
        return event_ids

    async def _refresh_all_caches(self) -> None:
        """Refresh cache for all events (no lock, eventual consistency)"""
        try:
            event_ids = await self._get_all_event_ids()

            for event_id in event_ids:
                stats = await self._fetch_all_stats(event_id)
                self._cache[event_id] = stats

            sum(len(sections) for sections in self._cache.values())
            # Logger.base.debug(
            #     f'💾 [CACHE] Refreshed {len(event_ids)} events, {total_sections} sections'
            # )
        except Exception as e:
            Logger.base.error(f'❌ [CACHE] Refresh failed: {e}')

    async def start_polling(self) -> None:
        """Start background polling for all events (0.5s interval)"""
        Logger.base.info('🔄 [POLLING] Starting seat availability cache polling')
        await self._refresh_all_caches()

        while True:
            await anyio.sleep(0.5)
            await self._refresh_all_caches()

    async def check_subsection_availability(
        self, *, event_id: UUID, section: str, subsection: int, required_quantity: int
    ) -> bool:
        """Check if subsection has sufficient seats (cache with Kvrocks fallback)"""
        with self.tracer.start_as_current_span('cache.check_availability') as span:
            section_id = f'{section}-{subsection}'

            # Try cache first
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

            # Fallback: query Kvrocks (for tests or before polling starts)
            Logger.base.debug(f'💾 [CACHE MISS] Querying Kvrocks for event {event_id}')
            span.set_attribute('cache_hit', False)

            client = kvrocks_client.get_client()
            stats_key = _make_key(f'section_stats:{event_id}:{section_id}')
            stats = await client.hgetall(stats_key)  # type: ignore

            if not stats:
                Logger.base.warning(f'⚠️ [AVAILABILITY] Section {section_id} not found')
                raise NotFoundError(f'Section {section_id} not found')

            available_count = int(stats.get('available', 0))
            has_enough = available_count >= required_quantity

            span.set_attribute('available_count', available_count)
            span.set_attribute('has_enough', has_enough)

            if has_enough:
                Logger.base.info(f'✅ [KVROCKS] {available_count} >= {required_quantity}')
            else:
                Logger.base.warning(f'❌ [KVROCKS] {available_count} < {required_quantity}')

            return has_enough
