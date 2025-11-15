"""
Unit tests for SeatStateCommandHandlerImpl._get_section_config

Test Focus:
1. Successfully retrieves section config from event config JSON
2. Config not found raises ValueError
3. Cache hit returns cached value (no Kvrocks call)
4. Cache miss fetches from Kvrocks and caches result
5. Multiple calls with same key use cache
6. JSON.GET with fallback to regular GET
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
        mock_client.get = AsyncMock()
        return mock_client

    @pytest.fixture
    def sample_event_state(self):
        """Sample event config JSON structure (hierarchical)"""
        return {
            'sections': {
                'A': {'price': 1000, 'subsections': {'1': {'rows': 10, 'seats_per_row': 15}}},
                'B': {'price': 2000, 'subsections': {'2': {'rows': 20, 'seats_per_row': 25}}},
            }
        }

    @pytest.mark.asyncio
    async def test_get_section_config_success_json_get(
        self, handler, mock_kvrocks_client, sample_event_state
    ):
        """Test successful retrieval using JSON.GET command"""
        # Given: Kvrocks supports JSON.GET and returns valid config
        config_json = orjson.dumps(sample_event_state).decode()
        mock_kvrocks_client.execute_command.return_value = [config_json]  # JSON.GET returns array

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When: Get section config
            result = await handler._get_section_config(event_id=1, section_id='A-1')

            # Then: Returns parsed config with price
            assert result == {'rows': 10, 'seats_per_row': 15, 'price': 1000}
            mock_kvrocks_client.execute_command.assert_called_once()
            mock_kvrocks_client.get.assert_not_called()  # Didn't fall back

    @pytest.mark.asyncio
    async def test_get_section_config_success_fallback_get(
        self, handler, mock_kvrocks_client, sample_event_state
    ):
        """Test successful retrieval using fallback GET when JSON.GET fails"""
        # Given: JSON.GET fails, fallback to regular GET
        config_json = orjson.dumps(sample_event_state).decode()
        mock_kvrocks_client.execute_command.side_effect = Exception('JSON commands not supported')
        mock_kvrocks_client.get.return_value = config_json

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When: Get section config
            result = await handler._get_section_config(event_id=1, section_id='A-1')

            # Then: Returns parsed config using fallback
            assert result == {'rows': 10, 'seats_per_row': 15, 'price': 1000}
            mock_kvrocks_client.execute_command.assert_called_once()
            mock_kvrocks_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_section_config_fallback_get_bytes(
        self, handler, mock_kvrocks_client, sample_event_state
    ):
        """Test fallback GET with bytes response"""
        # Given: GET returns bytes instead of string
        config_json = orjson.dumps(sample_event_state)
        mock_kvrocks_client.execute_command.side_effect = Exception('JSON not supported')
        mock_kvrocks_client.get.return_value = config_json  # bytes

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When: Get section config
            result = await handler._get_section_config(event_id=1, section_id='A-1')

            # Then: Correctly decodes bytes and returns config
            assert result == {'rows': 10, 'seats_per_row': 15, 'price': 1000}

    @pytest.mark.asyncio
    async def test_get_section_config_not_found(self, handler, mock_kvrocks_client):
        """Test ValueError when section not found in JSON"""
        # Given: Event config exists but section not in it (hierarchical structure)
        config_json = orjson.dumps(
            {
                'sections': {
                    'B': {'price': 500, 'subsections': {'1': {'rows': 5, 'seats_per_row': 10}}}
                }
            }
        ).decode()
        mock_kvrocks_client.execute_command.return_value = [config_json]

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When/Then: Raises ValueError for missing section
            with pytest.raises(ValueError, match='Section config not found: A-1'):
                await handler._get_section_config(event_id=1, section_id='A-1')

    @pytest.mark.asyncio
    async def test_get_section_config_empty_json(self, handler, mock_kvrocks_client):
        """Test ValueError when event config is empty"""
        # Given: Empty event config
        mock_kvrocks_client.execute_command.return_value = [None]
        mock_kvrocks_client.get.return_value = None

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When/Then: Raises ValueError
            with pytest.raises(ValueError, match='Section config not found'):
                await handler._get_section_config(event_id=1, section_id='A-1')

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
            mock_kvrocks_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_section_config_cache_miss_then_hit(
        self, handler, mock_kvrocks_client, sample_event_state
    ):
        """Test cache miss fetches from Kvrocks, subsequent call hits cache"""
        # Given: Kvrocks returns valid config
        config_json = orjson.dumps(sample_event_state).decode()
        mock_kvrocks_client.execute_command.return_value = [config_json]

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
        config_json = orjson.dumps(sample_event_state).decode()
        mock_kvrocks_client.execute_command.return_value = [config_json]

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
            # Both sections share same event config, so only 1 fetch
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
        # Given: Different event configs for different events (hierarchical structure)
        event1_config = {
            'sections': {
                'A': {'price': 1000, 'subsections': {'1': {'rows': 10, 'seats_per_row': 15}}}
            }
        }
        event2_config = {
            'sections': {
                'A': {'price': 2000, 'subsections': {'1': {'rows': 20, 'seats_per_row': 25}}}
            }
        }

        mock_kvrocks_client.execute_command.side_effect = [
            [orjson.dumps(event1_config).decode()],  # Event 1
            [orjson.dumps(event2_config).decode()],  # Event 2
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
    async def test_get_section_config_kvrocks_error_propagates(self, handler, mock_kvrocks_client):
        """Test Kvrocks errors result in section not found"""
        # Given: Both JSON.GET and fallback GET fail
        mock_kvrocks_client.execute_command.side_effect = Exception('JSON failed')
        mock_kvrocks_client.get.side_effect = Exception('Kvrocks connection failed')

        with patch(
            'src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl.kvrocks_client'
        ) as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_kvrocks_client

            # When/Then: Gracefully handles error and returns section not found
            with pytest.raises(Exception, match='Section config not found: A-1'):
                await handler._get_section_config(event_id=1, section_id='A-1')

    @pytest.mark.asyncio
    async def test_get_section_config_parses_values(
        self, handler, mock_kvrocks_client, sample_event_state
    ):
        """Test config values are parsed as integers"""
        # Given: JSON with numeric values
        config_json = orjson.dumps(sample_event_state).decode()
        mock_kvrocks_client.execute_command.return_value = [config_json]

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
