"""
Seating Config Query Handler Implementation

Reads seating config from Kvrocks (mirrors PostgreSQL seating_config).
Caches entire config per event_id with 10s TTL.
"""

import time
from typing import Any, Dict, TypedDict

from opentelemetry import trace
import orjson

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.reservation.app.interface.i_seating_config_query_handler import (
    ISeatingConfigQueryHandler,
)
from src.service.reservation.driven_adapter.state.reservation_helper.key_str_generator import (
    make_seating_config_key,
)
from src.service.shared_kernel.domain.value_object.subsection_config import SubsectionConfig


class CacheEntry(TypedDict):
    data: Dict[str, Any]  # Full seating_config JSON
    timestamp: float


class SeatingConfigQueryHandlerImpl(ISeatingConfigQueryHandler):
    """
    Seating Config Query Handler Implementation

    Reads from seating_config:{event_id} JSON in Kvrocks.
    Format: {"rows": 25, "cols": 20, "sections": [{"name": "A", "price": 3000, ...}]}

    Caches entire config per event_id with 10s TTL.
    """

    def __init__(self, *, ttl_seconds: float = 20.0) -> None:
        # Cache key: event_id → CacheEntry (entire config)
        self._cache: Dict[int, CacheEntry] = {}
        self._ttl_seconds = ttl_seconds
        self._tracer = trace.get_tracer(__name__)

    def _is_expired(self, *, entry: CacheEntry) -> bool:
        return time.time() - entry['timestamp'] > self._ttl_seconds

    async def get_config(self, *, event_id: int, section: str) -> SubsectionConfig:
        """Fetch seating config for a section from Kvrocks (cached with 10s TTL)."""
        with self._tracer.start_as_current_span(
            'config_handler.fetch_seating_config',
            attributes={'event.id': event_id, 'section': section},
        ) as span:
            # Check cache first
            if event_id in self._cache:
                entry = self._cache[event_id]
                if not self._is_expired(entry=entry):
                    span.set_attribute('cache_hit', True)
                    return self._extract_section_config(data=entry['data'], section=section)
                else:
                    span.set_attribute('cache_expired', True)

            span.set_attribute('cache_hit', False)

            # Fetch from Kvrocks
            client = kvrocks_client.get_client()
            key = make_seating_config_key(event_id=event_id)

            try:
                result = await client.execute_command('JSON.GET', key, '$')
                if isinstance(result, list) and result:
                    result = result[0]

                if not result:
                    raise ValueError(f'No seating_config found for event {event_id}')

                seating_config = orjson.loads(result)
                if isinstance(seating_config, list) and seating_config:
                    seating_config = seating_config[0]

                # Cache entire config
                self._cache[event_id] = {'data': seating_config, 'timestamp': time.time()}

                return self._extract_section_config(data=seating_config, section=section)

            except Exception as e:
                Logger.base.error(f'Failed to fetch seating config from Kvrocks: {e}')
                raise

    def _extract_section_config(self, *, data: Dict[str, Any], section: str) -> SubsectionConfig:
        """Extract SubsectionConfig from cached seating_config."""
        rows = data.get('rows', 0)
        cols = data.get('cols', 0)

        # Find section price
        sections = data.get('sections', [])
        price = 0
        for sec in sections:
            if sec.get('name') == section:
                price = sec.get('price', 0)
                break

        if not price:
            Logger.base.warning(f'Section {section} not found in config, using price=0')

        return SubsectionConfig(rows=rows, cols=cols, price=price)
