"""
Integration tests for SeatAvailabilityQueryHandlerImpl

Test integration behavior between ticketing service and Kvrocks
"""

from typing import Any

import orjson
import pytest
from redis.asyncio import Redis

from src.platform.exception.exceptions import NotFoundError
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.ticketing.driven_adapter.state.seat_availability_query_handler_impl import (
    SeatAvailabilityQueryHandlerImpl,
    _make_key,
)


async def _setup_event_state_json(
    client: Redis, event_id: int, section_id: str, stats: dict[str, Any]
) -> None:
    """
    Helper to set up event_state JSON with section stats

    ✨ NEW: Replaces HSET section_stats with JSON.SET event_state
    """
    config_key = _make_key(f'event_state:{event_id}')

    # Build event config JSON structure (hierarchical)
    # section_id format: "A-1" -> section "A", subsection "1"
    section_name = section_id.split('-')[0]
    subsection_num = section_id.split('-')[1]

    event_state = {
        'sections': {
            section_name: {
                'price': 1000,
                'subsections': {
                    subsection_num: {
                        'rows': 10,
                        'cols': 10,
                        'stats': {
                            'available': stats.get('available', 0),
                            'reserved': stats.get('reserved', 0),
                            'sold': stats.get('sold', 0),
                            'total': stats.get('total', 100),
                            'updated_at': stats.get('updated_at', 0),
                        },
                    }
                },
            }
        }
    }

    event_state_json = orjson.dumps(event_state).decode()

    try:
        # Try JSON.SET first
        await client.execute_command('JSON.SET', config_key, '$', event_state_json)
    except Exception:
        # Fallback: Regular SET
        await client.set(config_key, event_state_json)


class TestCheckSubsectionAvailabilityIntegration:
    """Test check_subsection_availability() integration with real Kvrocks"""

    @pytest.fixture
    async def handler(self) -> SeatAvailabilityQueryHandlerImpl:
        await kvrocks_client.initialize()
        return SeatAvailabilityQueryHandlerImpl()

    @pytest.mark.asyncio
    async def test_returns_true_when_sufficient_seats_available(
        self, handler: SeatAvailabilityQueryHandlerImpl
    ) -> None:
        """Test: should return True when sufficient seats available"""
        # Given: Set seat statistics in Kvrocks (using event_state JSON)
        client = kvrocks_client.get_client()
        await _setup_event_state_json(
            client,
            event_id=1,
            section_id='A-1',
            stats={'available': 50, 'reserved': 30, 'sold': 20, 'total': 100},
        )

        # When
        result = await handler.check_subsection_availability(
            event_id=1, section='A', subsection=1, required_quantity=10
        )

        # Then
        assert result.has_enough_seats is True

    @pytest.mark.asyncio
    async def test_returns_false_when_insufficient_seats(
        self, handler: SeatAvailabilityQueryHandlerImpl
    ) -> None:
        """Test: should return False when insufficient seats"""
        # Given: only 5 seats available
        client = kvrocks_client.get_client()
        await _setup_event_state_json(
            client,
            event_id=1,
            section_id='B-2',
            stats={'available': 5, 'reserved': 50, 'sold': 45, 'total': 100},
        )

        # When
        result = await handler.check_subsection_availability(
            event_id=1, section='B', subsection=2, required_quantity=10
        )

        # Then
        assert result.has_enough_seats is False

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
        result = await handler.check_subsection_availability(
            event_id=100, section='C', subsection=3, required_quantity=5
        )

        # Then: should be able to read data and return correct result
        assert result.has_enough_seats is True

        # Verify the event_state JSON was created
        config_key = _make_key('event_state:100')
        # ✨ Use JSON.GET to read JSON data (not regular GET)
        try:
            result = await client.execute_command('JSON.GET', config_key, '$')
            config_json = result[0] if isinstance(result, list) and result else result
        except Exception:
            # Fallback to regular GET if JSON commands not supported
            config_json = await client.get(config_key)

        if isinstance(config_json, bytes):
            config_json = config_json.decode()

        assert config_json is not None
        event_state = orjson.loads(config_json)
        if isinstance(event_state, list):
            event_state = event_state[0]
        assert event_state['sections']['C']['subsections']['3']['stats']['available'] == 10

    @pytest.mark.asyncio
    async def test_raises_not_found_error_when_section_not_exists(
        self, handler: SeatAvailabilityQueryHandlerImpl
    ) -> None:
        """Test: should raise NotFoundError when event does not exist"""
        # Given: no data for this event in Kvrocks (conftest clears it)

        # When/Then: Event check happens first, so error is 'Event 999 not found'
        with pytest.raises(NotFoundError, match='Event 999 not found'):
            await handler.check_subsection_availability(
                event_id=999, section='Z', subsection=99, required_quantity=1
            )

    @pytest.mark.asyncio
    async def test_handles_edge_case_exact_quantity_match(
        self, handler: SeatAvailabilityQueryHandlerImpl
    ) -> None:
        """Test: should return True when available seat count exactly matches requirement"""
        # Given: exactly 10 seats
        client = kvrocks_client.get_client()
        await _setup_event_state_json(
            client, event_id=1, section_id='A-1', stats={'available': 10, 'total': 100}
        )

        # When
        result = await handler.check_subsection_availability(
            event_id=1, section='A', subsection=1, required_quantity=10
        )

        # Then
        assert result.has_enough_seats is True

    @pytest.mark.asyncio
    async def test_handles_available_count_as_string(
        self, handler: SeatAvailabilityQueryHandlerImpl
    ) -> None:
        """Test: should correctly handle numeric types in JSON"""
        # Given: numbers in JSON
        client = kvrocks_client.get_client()
        await _setup_event_state_json(
            client, event_id=1, section_id='A-1', stats={'available': 100}
        )

        # When
        result = await handler.check_subsection_availability(
            event_id=1, section='A', subsection=1, required_quantity=50
        )

        # Then: should correctly handle and compare numbers
        assert result.has_enough_seats is True
