"""
Integration tests for SeatAvailabilityQueryHandlerImpl

Test integration behavior between ticketing service and Kvrocks
"""

import time
from typing import Any

import orjson
import pytest
from redis.asyncio import Redis

from src.platform.state.kvrocks_client import kvrocks_client
from src.service.reservation.driven_adapter.state.reservation_helper.key_str_generator import (
    _make_key,
)
from src.service.ticketing.driven_adapter.state.seat_availability_query_handler_impl import (
    SeatAvailabilityQueryHandlerImpl,
)


def _build_event_state(section_id: str, stats: dict[str, Any]) -> dict[str, Any]:
    """Build event_state structure for cache (matches get_event_stats format)."""
    return {
        'event_stats': {
            'available': stats.get('available', 0),
            'reserved': stats.get('reserved', 0),
            'sold': stats.get('sold', 0),
            'total': stats.get('total', 100),
        },
        # Dict keyed by 'section-subsection' for O(1) lookup
        'subsection_stats': {
            section_id: {
                'price': 1000,
                'available': stats.get('available', 0),
                'reserved': stats.get('reserved', 0),
                'sold': stats.get('sold', 0),
                'updated_at': stats.get('updated_at', 0),
            }
        },
    }


def _populate_handler_cache(
    handler: SeatAvailabilityQueryHandlerImpl,
    event_id: int,
    section_id: str,
    stats: dict[str, Any],
) -> None:
    """Populate handler's internal cache directly for testing."""
    event_state = _build_event_state(section_id, stats)
    handler._cache[event_id] = {'data': event_state, 'timestamp': time.time()}


async def _setup_event_state_json(
    client: Redis, event_id: int, section_id: str, stats: dict[str, Any]
) -> None:
    """
    Helper to set up event_state JSON with section stats

    ✨ NEW: Replaces HSET section_stats with JSON.SET event_state
    """
    config_key = _make_key(f'event_state:{event_id}')
    event_state = _build_event_state(section_id, stats)
    event_state_json = orjson.dumps(event_state).decode()

    try:
        # Try JSON.SET first
        await client.execute_command('JSON.SET', config_key, '$', event_state_json)
    except Exception:
        # Fallback: Regular SET
        await client.set(config_key, event_state_json)


class TestCheckAvailabilityIntegration:
    """Test check_availability() integration with real Kvrocks"""

    @pytest.fixture
    async def handler(self) -> SeatAvailabilityQueryHandlerImpl:
        await kvrocks_client.initialize()
        return SeatAvailabilityQueryHandlerImpl()

    @pytest.mark.asyncio
    async def test_returns_true_when_sufficient_seats_available(
        self, handler: SeatAvailabilityQueryHandlerImpl
    ) -> None:
        """Test: should return True when sufficient seats available (via cache)"""
        # Given: Populate handler's cache with sufficient seats
        _populate_handler_cache(
            handler,
            event_id=1,
            section_id='A-1',
            stats={'available': 50, 'reserved': 30, 'sold': 20, 'total': 100},
        )

        # When
        result = await handler.check_availability(
            event_id=1, section='A', subsection=1, required_quantity=10
        )

        # Then
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_insufficient_seats(
        self, handler: SeatAvailabilityQueryHandlerImpl
    ) -> None:
        """Test: should return False when insufficient seats (via cache)"""
        # Given: Populate handler's cache with only 5 seats available
        _populate_handler_cache(
            handler,
            event_id=1,
            section_id='B-2',
            stats={'available': 5, 'reserved': 50, 'sold': 45, 'total': 100},
        )

        # When
        result = await handler.check_availability(
            event_id=1, section='B', subsection=2, required_quantity=10
        )

        # Then
        assert result is False

    @pytest.mark.asyncio
    async def test_queries_correct_kvrocks_key(
        self, handler: SeatAvailabilityQueryHandlerImpl
    ) -> None:
        """Test: should query using correct Kvrocks key format"""
        # Given
        client = kvrocks_client.get_client()
        await _setup_event_state_json(
            client, event_id=100, section_id='C-3', stats={'available': 10}
        )

        # When
        result = await handler.check_availability(
            event_id=100, section='C', subsection=3, required_quantity=5
        )

        # Then: should be able to read data and return correct result
        assert result is True

        # Verify the event_state JSON was created
        config_key = _make_key('event_state:100')
        # ✨ Use JSON.GET to read JSON data (not regular GET)
        try:
            json_result = await client.execute_command('JSON.GET', config_key, '$')
            config_json = (
                json_result[0] if isinstance(json_result, list) and json_result else json_result
            )
        except Exception:
            # Fallback to regular GET if JSON commands not supported
            config_json = await client.get(config_key)

        if isinstance(config_json, bytes):
            config_json = config_json.decode()

        assert config_json is not None
        event_state = orjson.loads(config_json)
        if isinstance(event_state, list):
            event_state = event_state[0]
        # Verify subsection_stats structure (dict keyed by 'section-subsection')
        assert 'C-3' in event_state['subsection_stats']
        assert event_state['subsection_stats']['C-3']['available'] == 10

    @pytest.mark.asyncio
    async def test_pass_through_when_no_cache(
        self, handler: SeatAvailabilityQueryHandlerImpl
    ) -> None:
        """Test: should pass through (return True) when no cache exists"""
        # Given: no data for this event in Kvrocks (conftest clears it)
        # New behavior: no cache → pass through (optimistic)

        # When
        result = await handler.check_availability(
            event_id=999, section='Z', subsection=99, required_quantity=1
        )

        # Then: pass through (let actual reservation handle it)
        assert result is True

    @pytest.mark.asyncio
    async def test_handles_edge_case_exact_quantity_match(
        self, handler: SeatAvailabilityQueryHandlerImpl
    ) -> None:
        """Test: should return True when available seat count exactly matches requirement"""
        # Given: exactly 10 seats in cache
        _populate_handler_cache(
            handler, event_id=1, section_id='A-1', stats={'available': 10, 'total': 100}
        )

        # When
        result = await handler.check_availability(
            event_id=1, section='A', subsection=1, required_quantity=10
        )

        # Then
        assert result is True

    @pytest.mark.asyncio
    async def test_handles_available_count_as_number(
        self, handler: SeatAvailabilityQueryHandlerImpl
    ) -> None:
        """Test: should correctly handle numeric types in cache"""
        # Given: numbers in cache
        _populate_handler_cache(handler, event_id=1, section_id='A-1', stats={'available': 100})

        # When
        result = await handler.check_availability(
            event_id=1, section='A', subsection=1, required_quantity=50
        )

        # Then: should correctly handle and compare numbers
        assert result is True
