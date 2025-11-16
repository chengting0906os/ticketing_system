"""
Unit tests for SeatStateCommandHandlerImpl._get_section_config

Test Focus:
1. Successfully retrieves section config from event config JSON
2. Config not found raises ValueError
3. Cache hit returns cached value (no Kvrocks call)
4. Cache miss fetches from Kvrocks and caches result
5. Multiple calls with same key use cache
6. JSON.GET returns JSON array string
"""

import orjson
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
        mock_client.execute_command = AsyncMock()
        return mock_client

    @pytest.fixture
    def sample_event_state(self):
        """Sample event config JSON structure (hierarchical)"""
        return {
            'event_stats': {'available': 500, 'reserved': 0, 'sold': 0, 'total': 500},
            'sections': {
                'A': {'price': 1000, 'subsections': {'1': {'rows': 10, 'seats_per_row': 15}}},
                'B': {'price': 2000, 'subsections': {'2': {'rows': 20, 'seats_per_row': 25}}},
            },
        }

    @pytest.mark.asyncio
    async def test_get_section_config_success(self, handler, mock_kvrocks_client, sample_event_state):
        """Test successful retrieval using JSON.GET command"""
        # Given: Kvrocks returns JSON array string
        # JSON.GET with $ returns: '[{"event_stats":{...},"sections":{...}}]'
        json_array_string = orjson.dumps([sample_event_state]).decode()
        mock_kvrocks_client.execute_command.return_value = json_array_string

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When: Get section config
            result = await handler._get_section_config(event_id=1, section_id='A-1')

            # Then: Returns parsed config with price
            assert result == {'rows': 10, 'seats_per_row': 15, 'price': 1000}
            # Note: In tests, _make_key may add a prefix (e.g., 'test_gw3_')
            # We verify the call includes 'event_state:1' regardless of prefix
            call_args = mock_kvrocks_client.execute_command.call_args[0]
            assert call_args[0] == 'JSON.GET'
            assert 'event_state:1' in call_args[1]
            assert call_args[2] == '$'

    @pytest.mark.asyncio
    async def test_get_section_config_empty_result_raises_error(
        self, handler, mock_kvrocks_client
    ):
        """Test ValueError when JSON.GET returns None or empty"""
        # Given: JSON.GET returns None
        mock_kvrocks_client.execute_command.return_value = None

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When/Then: Raises ValueError
            with pytest.raises(ValueError, match='No event config found for event_id=1'):
                await handler._get_section_config(event_id=1, section_id='A-1')

    @pytest.mark.asyncio
    async def test_get_section_config_empty_array_raises_index_error(
        self, handler, mock_kvrocks_client
    ):
        """Test empty array raises IndexError when accessing first element"""
        # Given: JSON.GET returns empty array
        json_array_string = orjson.dumps([]).decode()
        mock_kvrocks_client.execute_command.return_value = json_array_string

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When/Then: Raises IndexError when accessing event_state_list[0]
            with pytest.raises(IndexError):
                await handler._get_section_config(event_id=1, section_id='A-1')

    @pytest.mark.asyncio
    async def test_get_section_config_section_not_found(
        self, handler, mock_kvrocks_client, sample_event_state
    ):
        """Test KeyError when section not found in JSON"""
        # Given: Event config exists but section 'Z' not in it
        json_array_string = orjson.dumps([sample_event_state]).decode()
        mock_kvrocks_client.execute_command.return_value = json_array_string

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When/Then: Raises KeyError when accessing subsection_config['rows']
            with pytest.raises(KeyError):
                await handler._get_section_config(event_id=1, section_id='Z-1')

    @pytest.mark.asyncio
    async def test_get_section_config_subsection_not_found(
        self, handler, mock_kvrocks_client, sample_event_state
    ):
        """Test KeyError when subsection not found in JSON"""
        # Given: Event config exists but subsection '99' not in section A
        json_array_string = orjson.dumps([sample_event_state]).decode()
        mock_kvrocks_client.execute_command.return_value = json_array_string

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When/Then: Raises KeyError when accessing subsection_config['rows']
            with pytest.raises(KeyError):
                await handler._get_section_config(event_id=1, section_id='A-99')

    @pytest.mark.asyncio
    async def test_get_section_config_cache_hit(self, handler, mock_kvrocks_client):
        """Test cache hit returns cached value without Kvrocks call"""
        # Given: Pre-populate cache
        handler._config_cache[(1, 'A-1')] = {'rows': 10, 'seats_per_row': 15, 'price': 1000}

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When: Get section config (should hit cache)
            result = await handler._get_section_config(event_id=1, section_id='A-1')

            # Then: Returns cached value, no Kvrocks call
            assert result == {'rows': 10, 'seats_per_row': 15, 'price': 1000}
            mock_kvrocks_client.execute_command.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_section_config_cache_miss_then_hit(
        self, handler, mock_kvrocks_client, sample_event_state
    ):
        """Test cache miss fetches from Kvrocks, subsequent call hits cache"""
        # Given: Kvrocks returns valid config
        json_array_string = orjson.dumps([sample_event_state]).decode()
        mock_kvrocks_client.execute_command.return_value = json_array_string

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When: First call (cache miss)
            result1 = await handler._get_section_config(event_id=1, section_id='A-1')

            # Then: Fetches from Kvrocks and caches
            assert result1 == {'rows': 10, 'seats_per_row': 15, 'price': 1000}
            assert mock_kvrocks_client.execute_command.call_count == 1

            # When: Second call (cache hit)
            result2 = await handler._get_section_config(event_id=1, section_id='A-1')

            # Then: Returns cached value, no additional Kvrocks call
            assert result2 == {'rows': 10, 'seats_per_row': 15, 'price': 1000}
            assert mock_kvrocks_client.execute_command.call_count == 1  # Still 1

    @pytest.mark.asyncio
    async def test_get_section_config_different_sections_cached_separately(
        self, handler, mock_kvrocks_client, sample_event_state
    ):
        """Test different sections are cached separately"""
        # Given: Event config with multiple sections
        json_array_string = orjson.dumps([sample_event_state]).decode()
        mock_kvrocks_client.execute_command.return_value = json_array_string

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When: Get configs for different sections (both fetch same event config)
            result1 = await handler._get_section_config(event_id=1, section_id='A-1')
            result2 = await handler._get_section_config(event_id=1, section_id='B-2')

            # Then: Each section cached separately with different values
            assert result1 == {'rows': 10, 'seats_per_row': 15, 'price': 1000}
            assert result2 == {'rows': 20, 'seats_per_row': 25, 'price': 2000}
            # Both sections fetch event config separately
            assert mock_kvrocks_client.execute_command.call_count == 2

            # When: Get same sections again (cache hit)
            result3 = await handler._get_section_config(event_id=1, section_id='A-1')
            result4 = await handler._get_section_config(event_id=1, section_id='B-2')

            # Then: Returns cached values, no additional calls
            assert result3 == {'rows': 10, 'seats_per_row': 15, 'price': 1000}
            assert result4 == {'rows': 20, 'seats_per_row': 25, 'price': 2000}
            assert mock_kvrocks_client.execute_command.call_count == 2  # Still 2

    @pytest.mark.asyncio
    async def test_get_section_config_different_events_cached_separately(
        self, handler, mock_kvrocks_client
    ):
        """Test same section in different events are cached separately"""
        # Given: Different event configs for different events
        event1_state = {
            'event_stats': {'available': 150, 'reserved': 0, 'sold': 0, 'total': 150},
            'sections': {
                'A': {'price': 1000, 'subsections': {'1': {'rows': 10, 'seats_per_row': 15}}}
            },
        }
        event2_state = {
            'event_stats': {'available': 500, 'reserved': 0, 'sold': 0, 'total': 500},
            'sections': {
                'A': {'price': 2000, 'subsections': {'1': {'rows': 20, 'seats_per_row': 25}}}
            },
        }

        mock_kvrocks_client.execute_command.side_effect = [
            orjson.dumps([event1_state]).decode(),  # Event 1
            orjson.dumps([event2_state]).decode(),  # Event 2
        ]

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When: Get same section for different events
            result1 = await handler._get_section_config(event_id=1, section_id='A-1')
            result2 = await handler._get_section_config(event_id=2, section_id='A-1')

            # Then: Each event's section cached separately
            assert result1 == {'rows': 10, 'seats_per_row': 15, 'price': 1000}
            assert result2 == {'rows': 20, 'seats_per_row': 25, 'price': 2000}
            assert (1, 'A-1') in handler._config_cache
            assert (2, 'A-1') in handler._config_cache
            assert handler._config_cache[(1, 'A-1')] != handler._config_cache[(2, 'A-1')]

    @pytest.mark.asyncio
    async def test_get_section_config_parses_values(
        self, handler, mock_kvrocks_client, sample_event_state
    ):
        """Test config values are parsed as integers"""
        # Given: JSON with numeric values
        json_array_string = orjson.dumps([sample_event_state]).decode()
        mock_kvrocks_client.execute_command.return_value = json_array_string

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When: Get section config
            result = await handler._get_section_config(event_id=1, section_id='A-1')

            # Then: All values parsed as integers
            assert result == {'rows': 10, 'seats_per_row': 15, 'price': 1000}
            assert isinstance(result['rows'], int)
            assert isinstance(result['seats_per_row'], int)
            assert isinstance(result['price'], int)

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
