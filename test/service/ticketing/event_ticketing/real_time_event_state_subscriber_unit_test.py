"""
Unit tests for RealTimeEventStateSubscriber

Tests the Redis Pub/Sub subscriber that receives real-time event_state updates
and updates the cache with throttling and automatic reconnection.
"""

from typing import Any
from unittest.mock import Mock

import orjson
import pytest

from src.service.ticketing.driven_adapter.state.real_time_event_state_subscriber import (
    RealTimeEventStateSubscriber,
)


class TestRealTimeEventStateSubscriber:
    @pytest.fixture
    def event_id(self) -> int:
        return 123

    @pytest.fixture
    def mock_cache_handler(self) -> Mock:
        """Mock ISeatAvailabilityQueryHandler"""
        handler = Mock()
        handler._cache = {}
        return handler

    @pytest.fixture
    def subscriber(self, event_id: int, mock_cache_handler: Mock) -> RealTimeEventStateSubscriber:
        """Create subscriber instance with default settings"""
        return RealTimeEventStateSubscriber(
            event_id=event_id,
            cache_handler=mock_cache_handler,
            throttle_interval=0.1,  # Shorter for testing
            reconnect_delay=0.1,  # Shorter for testing
        )

    @pytest.fixture
    def event_state_payload(self, event_id: int) -> dict[str, Any]:
        """Sample event_state update payload"""
        return {
            'event_id': event_id,
            'event_state': {
                'sections': [
                    {
                        'section': 'A',
                        'subsection': 1,
                        'available_seats': 95,
                        'total_seats': 100,
                    }
                ]
            },
        }

    # =========================================================================
    # Initialization Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_handle_update_success(
        self,
        subscriber: RealTimeEventStateSubscriber,
        event_state_payload: dict[str, Any],
        event_id: int,
    ) -> None:
        """Test successful message handling updates cache"""
        data = orjson.dumps(event_state_payload)

        await subscriber._handle_update(data)

        # Verify cache was updated
        assert event_id in subscriber.cache_handler._cache
        cache_entry = subscriber.cache_handler._cache[event_id]
        assert cache_entry['data'] == event_state_payload['event_state']
        assert 'timestamp' in cache_entry
        assert subscriber._last_apply_time > 0

    @pytest.mark.asyncio
    async def test_handle_update_invalid_json(
        self, subscriber: RealTimeEventStateSubscriber
    ) -> None:
        """Test handling of invalid JSON data"""
        invalid_data = b'not-valid-json'

        # Should not raise exception, just log warning
        await subscriber._handle_update(invalid_data)

        # Cache should remain empty
        assert len(subscriber.cache_handler._cache) == 0

    @pytest.mark.asyncio
    async def test_handle_update_missing_fields(
        self, subscriber: RealTimeEventStateSubscriber
    ) -> None:
        """Test handling of payload with missing required fields"""
        incomplete_payload = {'event_id': 123}  # Missing 'event_state'
        data = orjson.dumps(incomplete_payload)

        # Should not raise exception, just log warning
        await subscriber._handle_update(data)

        # Cache should remain empty
        assert len(subscriber.cache_handler._cache) == 0

    # =========================================================================
    # Message Processing Tests (without full loop)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_handle_message_processing(
        self,
        subscriber: RealTimeEventStateSubscriber,
        event_state_payload: dict[str, Any],
        event_id: int,
    ) -> None:
        """Test that _handle_update correctly processes message data"""
        data = orjson.dumps(event_state_payload)

        # Call _handle_update directly (bypassing the subscribe loop)
        await subscriber._handle_update(data)

        # Verify cache entry structure
        assert event_id in subscriber.cache_handler._cache
        cache_entry = subscriber.cache_handler._cache[event_id]

        # Verify data structure
        assert 'data' in cache_entry
        assert 'timestamp' in cache_entry
        assert isinstance(cache_entry['data'], dict)
        assert 'sections' in cache_entry['data']

    # =========================================================================
    # Channel Configuration Tests
    # =========================================================================

    def test_channel_format(self, subscriber: RealTimeEventStateSubscriber, event_id: int) -> None:
        """Test that channel name follows expected format"""
        expected_channel = f'event_state_updates:{event_id}'
        assert subscriber.channel == expected_channel

    def test_different_event_ids_have_different_channels(self, mock_cache_handler: Mock) -> None:
        """Test that different event IDs get different channels"""
        subscriber1 = RealTimeEventStateSubscriber(event_id=100, cache_handler=mock_cache_handler)
        subscriber2 = RealTimeEventStateSubscriber(event_id=200, cache_handler=mock_cache_handler)

        assert subscriber1.channel != subscriber2.channel
        assert subscriber1.channel == 'event_state_updates:100'
        assert subscriber2.channel == 'event_state_updates:200'

    # =========================================================================
    # Error Handling Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_handle_update_with_malformed_data(
        self, subscriber: RealTimeEventStateSubscriber
    ) -> None:
        """Test handling of malformed but valid JSON"""
        malformed_payload = {'unexpected': 'structure'}
        data = orjson.dumps(malformed_payload)

        # Should not raise exception
        await subscriber._handle_update(data)

        # Cache should remain empty
        assert len(subscriber.cache_handler._cache) == 0

    @pytest.mark.asyncio
    async def test_handle_update_with_wrong_event_id(
        self, subscriber: RealTimeEventStateSubscriber, event_id: int
    ) -> None:
        """Test handling of update for different event ID"""
        wrong_id_payload = {
            'event_id': 999,  # Different from subscriber's event_id
            'event_state': {'sections': []},
        }
        data = orjson.dumps(wrong_id_payload)

        await subscriber._handle_update(data)

        # Cache should have entry for wrong event ID (as designed)
        assert 999 in subscriber.cache_handler._cache
        # Original event ID should not be in cache
        assert event_id not in subscriber.cache_handler._cache
