"""
Unit tests for SeatStateCommandHandlerImpl._get_section_config

Test Focus:
1. Successfully retrieves section config from Kvrocks
2. Config not found raises ValueError
3. Cache hit returns cached value (no Kvrocks call)
4. Cache miss fetches from Kvrocks and caches result
5. Multiple calls with same key use cache
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl import (
    SeatStateCommandHandlerImpl,
)


@pytest.mark.unit
class TestGetSectionConfig:
    """Test suite for _get_section_config method"""

    @pytest.fixture
    def handler(self):
        """Create handler instance with mocked booking metadata handler"""
        # Mock the booking metadata handler
        mock_metadata_handler = MagicMock()
        return SeatStateCommandHandlerImpl(booking_metadata_handler=mock_metadata_handler)

    @pytest.fixture
    def mock_kvrocks_client(self):
        """Mock Kvrocks client"""
        mock_client = MagicMock()
        mock_client.hgetall = AsyncMock()
        return mock_client

    @pytest.mark.asyncio
    async def test_get_section_config_success(self, handler, mock_kvrocks_client):
        """Test successful retrieval of section config"""
        # Given: Kvrocks returns valid config (string keys)
        mock_kvrocks_client.hgetall.return_value = {
            'rows': '10',
            'seats_per_row': '15',
        }

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When: Get section config
            result = await handler._get_section_config(event_id=1, section_id='A-1')

            # Then: Returns parsed config
            assert result == {'rows': 10, 'seats_per_row': 15}
            mock_kvrocks_client.hgetall.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_section_config_not_found(self, handler, mock_kvrocks_client):
        """Test ValueError when config not found"""
        # Given: Kvrocks returns empty dict (config not found)
        mock_kvrocks_client.hgetall.return_value = {}

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When/Then: Raises ValueError
            with pytest.raises(ValueError, match='Section config not found: A-1'):
                await handler._get_section_config(event_id=1, section_id='A-1')

    @pytest.mark.asyncio
    async def test_get_section_config_cache_hit(self, handler, mock_kvrocks_client):
        """Test cache hit returns cached value without Kvrocks call"""
        # Given: Pre-populate cache
        handler._config_cache[(1, 'A-1')] = {'rows': 10, 'seats_per_row': 15}

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When: Get section config (should hit cache)
            result = await handler._get_section_config(event_id=1, section_id='A-1')

            # Then: Returns cached value, no Kvrocks call
            assert result == {'rows': 10, 'seats_per_row': 15}
            mock_kvrocks_client.hgetall.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_section_config_cache_miss_then_hit(self, handler, mock_kvrocks_client):
        """Test cache miss fetches from Kvrocks, subsequent call hits cache"""
        # Given: Kvrocks returns valid config (string keys)
        mock_kvrocks_client.hgetall.return_value = {
            'rows': '10',
            'seats_per_row': '15',
        }

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When: First call (cache miss)
            result1 = await handler._get_section_config(event_id=1, section_id='A-1')

            # Then: Fetches from Kvrocks and caches
            assert result1 == {'rows': 10, 'seats_per_row': 15}
            assert mock_kvrocks_client.hgetall.call_count == 1

            # When: Second call (cache hit)
            result2 = await handler._get_section_config(event_id=1, section_id='A-1')

            # Then: Returns cached value, no additional Kvrocks call
            assert result2 == {'rows': 10, 'seats_per_row': 15}
            assert mock_kvrocks_client.hgetall.call_count == 1  # Still 1 (no new call)

    @pytest.mark.asyncio
    async def test_get_section_config_different_sections_cached_separately(
        self, handler, mock_kvrocks_client
    ):
        """Test different sections are cached separately"""

        # Given: Kvrocks returns different configs for different sections (string keys)
        def mock_hgetall_side_effect(key):
            if 'A-1' in str(key):
                return {'rows': '10', 'seats_per_row': '15'}
            elif 'B-2' in str(key):
                return {'rows': '20', 'seats_per_row': '25'}
            return {}

        mock_kvrocks_client.hgetall.side_effect = mock_hgetall_side_effect

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When: Get configs for different sections
            result1 = await handler._get_section_config(event_id=1, section_id='A-1')
            result2 = await handler._get_section_config(event_id=1, section_id='B-2')

            # Then: Each section cached separately
            assert result1 == {'rows': 10, 'seats_per_row': 15}
            assert result2 == {'rows': 20, 'seats_per_row': 25}
            assert mock_kvrocks_client.hgetall.call_count == 2

            # When: Get same sections again (cache hit)
            result3 = await handler._get_section_config(event_id=1, section_id='A-1')
            result4 = await handler._get_section_config(event_id=1, section_id='B-2')

            # Then: Returns cached values, no additional calls
            assert result3 == {'rows': 10, 'seats_per_row': 15}
            assert result4 == {'rows': 20, 'seats_per_row': 25}
            assert mock_kvrocks_client.hgetall.call_count == 2  # Still 2

    @pytest.mark.asyncio
    async def test_get_section_config_different_events_cached_separately(
        self, handler, mock_kvrocks_client
    ):
        """Test same section in different events are cached separately"""
        # Given: Kvrocks returns different configs for different events (string keys)
        mock_kvrocks_client.hgetall.side_effect = [
            {'rows': '10', 'seats_per_row': '15'},  # Event 1
            {'rows': '20', 'seats_per_row': '25'},  # Event 2
        ]

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When: Get same section for different events
            result1 = await handler._get_section_config(event_id=1, section_id='A-1')
            result2 = await handler._get_section_config(event_id=2, section_id='A-1')

            # Then: Each event's section cached separately
            assert result1 == {'rows': 10, 'seats_per_row': 15}
            assert result2 == {'rows': 20, 'seats_per_row': 25}
            assert (1, 'A-1') in handler._config_cache
            assert (2, 'A-1') in handler._config_cache
            assert handler._config_cache[(1, 'A-1')] != handler._config_cache[(2, 'A-1')]

    @pytest.mark.asyncio
    async def test_get_section_config_kvrocks_error_propagates(self, handler, mock_kvrocks_client):
        """Test Kvrocks errors are propagated"""
        # Given: Kvrocks raises exception
        mock_kvrocks_client.hgetall.side_effect = Exception('Kvrocks connection failed')

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When/Then: Exception propagates
            with pytest.raises(Exception, match='Kvrocks connection failed'):
                await handler._get_section_config(event_id=1, section_id='A-1')

    @pytest.mark.asyncio
    async def test_get_section_config_parses_string_values(self, handler, mock_kvrocks_client):
        """Test config values are parsed as integers (not bytes/strings)"""
        # Given: Kvrocks returns string values (common scenario)
        mock_kvrocks_client.hgetall.return_value = {
            'rows': '10',  # String, not bytes
            'seats_per_row': '15',
        }

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When: Get section config
            result = await handler._get_section_config(event_id=1, section_id='A-1')

            # Then: Values parsed as integers
            assert result == {'rows': 10, 'seats_per_row': 15}
            assert isinstance(result['rows'], int)
            assert isinstance(result['seats_per_row'], int)

    @pytest.mark.asyncio
    async def test_cache_initialization_in_constructor(self):
        """Test cache is initialized in constructor"""
        # Given/When: Create handler
        mock_metadata_handler = MagicMock()
        handler = SeatStateCommandHandlerImpl(booking_metadata_handler=mock_metadata_handler)

        # Then: Cache is initialized as empty dict
        assert hasattr(handler, '_config_cache')
        assert isinstance(handler._config_cache, dict)
        assert len(handler._config_cache) == 0
