"""
Unit tests for AtomicReservationExecutor

Tests atomic seat reservation execution using Redis pipelines,
focusing on data consistency and proper handling of seat states,
statistics, and booking metadata.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import orjson
import pytest

from src.service.seat_reservation.driven_adapter.seat_reservation_helper import (
    atomic_reservation_executor,
)
from src.service.seat_reservation.driven_adapter.seat_reservation_helper.atomic_reservation_executor import (
    AtomicReservationExecutor,
)


# Test constants - attribute name for patching
KVROCKS_CLIENT_ATTR = 'kvrocks_client'


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def executor():
    return AtomicReservationExecutor()


@pytest.fixture
def mock_kvrocks_client():
    client = MagicMock()
    pipeline = MagicMock()
    client.pipeline.return_value = pipeline
    return client, pipeline


@pytest.fixture
def sample_seats():
    return [
        (1, 1, 0, 'A-1-1-1'),  # (row, seat_num, seat_index, seat_id)
        (1, 2, 1, 'A-1-1-2'),
    ]


# ============================================================================
# Test _decode_stats
# ============================================================================


@pytest.mark.unit
class TestDecodeStats:
    def test_decode_stats_with_bytes(self, executor):
        """Test decoding stats when Redis returns bytes"""
        # Given: Stats with byte keys and values
        stats_raw = {
            b'available': b'99',
            b'reserved': b'1',
            b'sold': b'0',
            b'total': b'100',
        }

        # When: Decode stats
        result = executor._decode_stats(stats_raw)

        # Then: Should convert bytes to proper dict
        assert result == {
            'available': 99,
            'reserved': 1,
            'sold': 0,
            'total': 100,
        }

    def test_decode_stats_with_strings(self, executor):
        # Given: Stats with string keys and values
        stats_raw = {
            'available': '99',
            'reserved': '1',
            'sold': '0',
            'total': '100',
        }

        # When: Decode stats
        result = executor._decode_stats(stats_raw)

        # Then: Should convert strings to proper dict
        assert result == {
            'available': 99,
            'reserved': 1,
            'sold': 0,
            'total': 100,
        }

    def test_decode_stats_mixed_types(self, executor):
        # Given: Stats with mixed types
        stats_raw = {
            b'available': '99',  # byte key, string value
            'reserved': b'1',  # string key, byte value
            b'sold': b'0',  # both bytes
            'total': '100',  # both strings
        }

        # When: Decode stats
        result = executor._decode_stats(stats_raw)

        # Then: Should handle mixed types correctly
        assert result == {
            'available': 99,
            'reserved': 1,
            'sold': 0,
            'total': 100,
        }

    def test_decode_stats_empty_dict(self, executor):
        # Given: Empty stats
        stats_raw = {}

        # When: Decode stats
        result = executor._decode_stats(stats_raw)

        # Then: Should return empty dict
        assert result == {}

    def test_decode_stats_none(self, executor):
        # Given: None stats
        stats_raw = None

        # When: Decode stats
        result = executor._decode_stats(stats_raw)

        # Then: Should return empty dict
        assert result == {}

    def test_decode_stats_invalid_values(self, executor):
        # Given: Stats with invalid values
        stats_raw = {
            b'available': b'invalid',
            b'reserved': b'',
            b'sold': None,
        }

        # When: Decode stats
        result = executor._decode_stats(stats_raw)

        # Then: Should default to 0 for values that can't be converted to int
        assert result == {
            'available': 0,  # Convert invalid to 0
            'reserved': 0,  # Convert empty string to 0
            'sold': 0,  # Convert None to 0
        }


# ============================================================================
# Test _parse_json_get_result
# ============================================================================


@pytest.mark.unit
class TestParseJsonGetResult:
    """Test JSON.GET result parsing logic"""

    def test_parse_json_get_result_bytes(self):
        """Test parsing when JSON.GET returns bytes (Kvrocks format)"""
        # Given: JSON.GET result as bytes containing JSON array (what Kvrocks actually returns)
        event_state_json = {
            'event_stats': {
                'available': 0,
                'reserved': 500,
                'sold': 0,
                'total': 500,
                'updated_at': 1763299859,
            },
            'sections': {
                'A': {
                    'price': 3000,
                    'subsections': {
                        '1': {
                            'rows': 1,
                            'seats_per_row': 5,
                            'stats': {
                                'available': 0,
                                'reserved': 5,
                                'sold': 0,
                                'total': 5,
                                'updated_at': 1763299859,
                            },
                        }
                    },
                }
            },
        }
        # Kvrocks returns bytes like b'[{...}]' (bytes representing JSON array)
        json_config_result = orjson.dumps([event_state_json])

        # When: Parse result (simulating the parsing logic)
        # Kvrocks returns bytes directly (not wrapped in a list)
        if isinstance(json_config_result, list) and json_config_result:
            config_json = json_config_result[0]
        elif isinstance(json_config_result, bytes):
            config_json = json_config_result.decode()
        else:
            config_json = json_config_result

        # Then: Should parse bytes correctly
        # config_json is now a string like '[{...}]'
        parsed = orjson.loads(config_json)
        # Extract first element from array
        if isinstance(parsed, list) and parsed:
            parsed = parsed[0]
        assert parsed == event_state_json
        assert parsed['event_stats']['available'] == 0
        assert parsed['sections']['A']['price'] == 3000

    def test_parse_json_get_result_list_with_bytes(self):
        """Test parsing when JSON.GET returns list[bytes]"""
        # Given: JSON.GET result as list containing bytes
        event_state_json = {'event_stats': {'available': 100}}
        json_config_result = [orjson.dumps(event_state_json)]  # bytes in list

        # When: Parse result (orjson.loads can handle bytes directly)
        config_json: bytes = json_config_result[0]  # Extract bytes from list

        # Then: orjson.loads should handle bytes directly without decode
        # ✅ Correct: Pass bytes directly to orjson.loads
        parsed = orjson.loads(config_json)  # config_json is bytes
        assert parsed == event_state_json
        assert isinstance(config_json, bytes)  # Verify we're testing bytes handling

    def test_parse_json_get_result_empty_list(self):
        """Test parsing when JSON.GET returns empty list"""
        # Given: Empty list
        json_config_result = []

        # When: Parse result
        if isinstance(json_config_result, list) and json_config_result:
            config_json = json_config_result[0]
        else:
            config_json = json_config_result

        # Then: Should return empty list (will cause error later, which is expected)
        assert config_json == []

    def test_parse_json_get_result_simplified_logic(self):
        """Test simplified parsing logic with bytes (Kvrocks format)"""
        # Given: Standard Kvrocks JSON.GET result format (bytes)
        event_state_json = {
            'event_stats': {'available': 500},
            'sections': {'A': {'price': 3000}},
        }
        # Kvrocks returns bytes like b'[{...}]'
        json_config_result = orjson.dumps([event_state_json])

        # When: Parse bytes directly (orjson.loads handles bytes)
        parsed = orjson.loads(json_config_result)
        # Extract first element from array
        if isinstance(parsed, list) and parsed:
            parsed = parsed[0]

        # Then: Should work correctly
        assert parsed == event_state_json


@pytest.mark.unit
class TestParseEventStatsJsonPath:
    """Test JSON.GET $.event_stats parsing logic (JSONPath format always returns list[dict])"""

    def test_parse_event_stats_bytes(self):
        """Test parsing when JSON.GET $.event_stats returns bytes (Kvrocks format)"""
        # Given: JSON.GET $.event_stats result as bytes (what Kvrocks actually returns)
        event_stats = {
            'available': 100,
            'reserved': 400,
            'sold': 0,
            'total': 500,
            'updated_at': 1763299859,
        }
        # Kvrocks returns bytes like b'[{...}]' (JSON array containing the stats)
        stats_result = orjson.dumps([event_stats])

        # When: Parse bytes directly (orjson.loads handles bytes)
        parsed = orjson.loads(stats_result)
        # Extract first element from array
        if isinstance(parsed, list) and parsed:
            parsed_stats = parsed[0]
        else:
            parsed_stats = parsed

        # Then: Should extract dict correctly
        assert parsed_stats == event_stats
        assert parsed_stats['available'] == 100
        assert parsed_stats['total'] == 500

    def test_parse_event_stats_direct_parse(self):
        """Test direct parsing of bytes without intermediate steps"""
        # Given: JSON.GET result as bytes
        event_stats = {'available': 250, 'reserved': 250, 'sold': 0, 'total': 500}
        stats_result = orjson.dumps([event_stats])  # Kvrocks returns bytes

        # When: Parse bytes directly (most efficient)
        parsed = orjson.loads(stats_result)
        parsed_stats = parsed[0] if isinstance(parsed, list) else parsed

        # Then: Should handle bytes correctly
        assert parsed_stats == event_stats

    def test_parse_event_stats_empty_result(self):
        """Test parsing when JSON.GET $.event_stats returns empty list (key not found)"""
        # Given: Empty list (JSONPath returns [] when path not found)
        stats_result = []

        # When/Then: Should raise IndexError when trying to access first element
        with pytest.raises(IndexError):
            _ = stats_result[0]  # This triggers fallback in production code

    def test_parse_event_stats_null_result(self):
        """Test parsing when JSON.GET $.event_stats returns [null]"""
        # Given: List with null value
        stats_result = ['null']

        # When: Parse result
        stats_json = stats_result[0]
        if isinstance(stats_json, bytes):
            stats_json = stats_json.decode()
        parsed_stats = orjson.loads(stats_json)

        # Then: Should return None (triggers fallback to full JSON.GET)
        assert parsed_stats is None


# ============================================================================
# Test fetch_total_price
# ============================================================================


@pytest.mark.unit
class TestFetchTotalPrice:
    @pytest.mark.asyncio
    async def test_fetch_total_price_success(self, executor, sample_seats):
        # Given: Mock Kvrocks client with event config JSON
        with patch.object(atomic_reservation_executor, KVROCKS_CLIENT_ATTR) as mock_kvrocks:
            mock_client = MagicMock()
            mock_kvrocks.get_client.return_value = mock_client

            # Mock event config JSON with hierarchical structure (price at section level)
            event_state = {
                'sections': {
                    'A': {'price': 1000, 'subsections': {'1': {'rows': 25, 'seats_per_row': 20}}}
                }
            }

            # Mock JSON.GET command - Kvrocks returns bytes like b'[{...}]'
            result_bytes = orjson.dumps([event_state])  # Wrap in list, get bytes
            mock_client.execute_command = AsyncMock(return_value=result_bytes)

            total_price = await executor.fetch_total_price(
                event_id=123,
                section_id='A-1',
                seats_to_reserve=sample_seats,
            )

            assert total_price == 2000

            # And: Should call JSON.GET once
            mock_client.execute_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_total_price_missing_section(self, executor):
        # Given: Seats but section config not found in JSON
        seats = [
            (1, 1, 0, 'A-1-1-1'),
            (1, 2, 1, 'A-1-1-2'),
            (1, 3, 2, 'A-1-1-3'),
        ]

        with patch.object(atomic_reservation_executor, KVROCKS_CLIENT_ATTR) as mock_kvrocks:
            mock_client = MagicMock()
            mock_kvrocks.get_client.return_value = mock_client

            # Mock event config JSON without the requested section (hierarchical structure)
            event_state = {
                'sections': {
                    'B': {'price': 2000, 'subsections': {'1': {'rows': 20, 'seats_per_row': 15}}}
                }
            }
            # Mock JSON.GET command - Kvrocks returns bytes like b'[{...}]'
            result_bytes = orjson.dumps([event_state])
            mock_client.execute_command = AsyncMock(return_value=result_bytes)

            total_price = await executor.fetch_total_price(
                event_id=123,
                section_id='A-1',  # Not in config
                seats_to_reserve=seats,
            )

            # Then: Missing section should default to price 0, so total is 0
            assert total_price == 0

    @pytest.mark.asyncio
    async def test_fetch_total_price_multiple_seats(self, executor):
        # Given: Multiple seats in the same section
        seats_a1 = [
            (1, 1, 0, 'A-1-1-1'),
            (1, 2, 1, 'A-1-1-2'),
        ]

        with patch.object(atomic_reservation_executor, KVROCKS_CLIENT_ATTR) as mock_kvrocks:
            mock_client = MagicMock()
            mock_kvrocks.get_client.return_value = mock_client

            # Mock event config JSON with hierarchical structure (price 1000 at section level)
            event_state = {
                'sections': {
                    'A': {'price': 1000, 'subsections': {'1': {'rows': 25, 'seats_per_row': 20}}}
                }
            }
            # Mock JSON.GET command - Kvrocks returns bytes like b'[{...}]'
            result_bytes = orjson.dumps([event_state])
            mock_client.execute_command = AsyncMock(return_value=result_bytes)

            # When: Fetch total price for 2 seats in A-1
            total_price = await executor.fetch_total_price(
                event_id=123,
                section_id='A-1',
                seats_to_reserve=seats_a1,
            )

            # Then: All seats in same section have same price (1000 * 2 = 2000)
            assert total_price == 2000


# ============================================================================
# Test execute_atomic_reservation
# ============================================================================


@pytest.mark.unit
class TestExecuteAtomicReservation:
    @pytest.mark.asyncio
    async def test_execute_atomic_reservation_success(self, executor, sample_seats):
        # Given: Mock Kvrocks client and pipeline
        with patch.object(atomic_reservation_executor, KVROCKS_CLIENT_ATTR) as mock_kvrocks:
            mock_client = MagicMock()
            mock_pipeline = MagicMock()
            mock_kvrocks.get_client.return_value = mock_client
            mock_client.pipeline.return_value = mock_pipeline

            # Mock current event stats (for time tracking via JSON.GET)
            # execute_command is called for JSON.GET $.event_stats (returns bytes)
            mock_client.execute_command = AsyncMock(
                return_value=b'[{"reserved":0,"sold":0,"available":500,"total":500}]'
            )

            # Mock pipeline execution results
            # ✨ NEW: 4 setbit + 4 JSON.NUMINCRBY + 1 JSON.GET + 1 HSET = 10 results
            mock_pipeline.execute = AsyncMock(
                return_value=[
                    # Setbit results (2 seats × 2 bits = 4 results)
                    1,
                    1,  # Seat 1: bit0, bit1
                    1,
                    1,  # Seat 2: bit0, bit1
                    # JSON.NUMINCRBY section stats (2 results - returns new values)
                    [98],  # section available (after decrement)
                    [2],  # section reserved (after increment)
                    # JSON.NUMINCRBY event stats (2 results - returns new values)
                    [498],  # event available
                    [2],  # event reserved
                    # JSON.GET result from pipeline (bytes from Kvrocks)
                    b'[{"sections":{"A":{"price":1000,"subsections":{"1":{"stats":{"available":98,"reserved":2,"sold":0,"total":100}}}}},"event_stats":{"available":498,"reserved":2,"sold":0,"total":500}}]',
                    # HSET result (1 result)
                    4,  # Number of fields set
                ]
            )

            # When: Execute atomic reservation
            result = await executor.execute_atomic_reservation(
                event_id=123,
                section_id='A-1',
                booking_id='booking-123',
                bf_key='seats_bf:123:A-1',
                seats_to_reserve=sample_seats,
                total_price=2000,
            )

            # Then: Should return success result
            assert result['success'] is True
            assert result['reserved_seats'] == ['A-1-1-1', 'A-1-1-2']
            assert result['total_price'] == 2000
            assert result['subsection_stats'] == {
                'available': 98,
                'reserved': 2,
                'sold': 0,
                'total': 100,
            }
            assert result['event_stats'] == {
                'available': 498,
                'reserved': 2,
                'sold': 0,
                'total': 500,
            }
            assert result['error_message'] is None

            # And: Should have called setbit for each seat
            assert mock_pipeline.setbit.call_count == 4  # 2 seats × 2 bits

            # And: ✨ NEW: Should have called execute_command for JSON operations
            # JSON.NUMINCRBY × 4 (section stats × 2 + event stats × 2)
            # JSON.GET × 1 (fetch complete event_state)
            assert mock_pipeline.execute_command.call_count == 5

            # And: Should have called hset for booking metadata
            assert mock_pipeline.hset.call_count == 1

    @pytest.mark.asyncio
    async def test_execute_atomic_reservation_single_seat(self, executor):
        # Given: Single seat reservation
        seats = [(1, 1, 0, 'A-1-1-1')]

        with patch.object(atomic_reservation_executor, KVROCKS_CLIENT_ATTR) as mock_kvrocks:
            mock_client = MagicMock()
            mock_pipeline = MagicMock()
            mock_kvrocks.get_client.return_value = mock_client
            mock_client.pipeline.return_value = mock_pipeline

            # Mock current event stats (for time tracking via JSON.GET)
            # execute_command is called for JSON.GET $.event_stats
            mock_client.execute_command = AsyncMock(
                return_value=b'[{"reserved":0,"sold":0,"available":500,"total":500}]'
            )

            # Mock pipeline results for 1 seat
            # ✨ NEW: 2 setbit + 4 JSON.NUMINCRBY + 1 JSON.GET + 1 HSET = 8 results
            mock_pipeline.execute = AsyncMock(
                return_value=[
                    # Setbit results (1 seat × 2 bits = 2 results)
                    1,
                    1,
                    # JSON.NUMINCRBY section stats (2 results - returns new values)
                    [99],  # available (after decrement)
                    [1],  # reserved (after increment)
                    # JSON.NUMINCRBY event stats (2 results - returns new values)
                    [499],  # event available
                    [1],  # event reserved
                    # JSON.GET result from pipeline (bytes from Kvrocks)
                    b'[{"sections":{"A":{"price":1000,"subsections":{"1":{"stats":{"available":99,"reserved":1,"sold":0,"total":100}}}}},"event_stats":{"available":499,"reserved":1,"sold":0,"total":500}}]',
                    # HSET result (1 result)
                    4,
                ]
            )

            # When: Execute atomic reservation
            result = await executor.execute_atomic_reservation(
                event_id=123,
                section_id='A-1',
                booking_id='booking-123',
                bf_key='seats_bf:123:A-1',
                seats_to_reserve=seats,
                total_price=1000,
            )

            # Then: Should correctly handle single seat
            assert result['success'] is True
            assert result['reserved_seats'] == ['A-1-1-1']
            assert result['total_price'] == 1000

            # And: Stats should be parsed from JSON correctly
            # For 1 seat: 2 setbit + 4 JSON.NUMINCRBY (section x2 + event x2) + JSON.GET at idx 6
            assert result['subsection_stats'] == {
                'available': 99,
                'reserved': 1,
                'sold': 0,
                'total': 100,
            }
            assert result['event_stats'] == {
                'available': 499,
                'reserved': 1,
                'sold': 0,
                'total': 500,
            }

    @pytest.mark.asyncio
    async def test_execute_atomic_reservation_multiple_seats(self, executor):
        # Given: 5 seats reservation
        seats = [
            (1, 1, 0, 'A-1-1-1'),
            (1, 2, 1, 'A-1-1-2'),
            (1, 3, 2, 'A-1-1-3'),
            (2, 1, 3, 'A-1-2-1'),
            (2, 2, 4, 'A-1-2-2'),
        ]

        with patch.object(atomic_reservation_executor, KVROCKS_CLIENT_ATTR) as mock_kvrocks:
            mock_client = MagicMock()
            mock_pipeline = MagicMock()
            mock_kvrocks.get_client.return_value = mock_client
            mock_client.pipeline.return_value = mock_pipeline

            # Mock current event stats (for time tracking via JSON.GET)
            # execute_command is called for JSON.GET $.event_stats
            mock_client.execute_command = AsyncMock(
                return_value=b'[{"reserved":0,"sold":0,"available":500,"total":500}]'
            )

            # Mock pipeline results for 5 seats
            # ✨ NEW: 10 setbit + 4 JSON.NUMINCRBY + 1 JSON.GET + 1 HSET = 16 results
            setbit_results = [1] * 10  # 5 seats × 2 bits
            json_numincrby_section_results = [[95], [5]]  # section stats (returns new values)
            json_numincrby_event_results = [[495], [5]]  # event stats
            # JSON.GET from pipeline returns bytes
            json_get_result = [
                b'[{"sections":{"A":{"price":1000,"subsections":{"1":{"stats":{"available":95,"reserved":5,"sold":0,"total":100}}}}},"event_stats":{"available":495,"reserved":5,"sold":0,"total":500}}]'
            ]
            hset_result = [4]

            mock_pipeline.execute = AsyncMock(
                return_value=setbit_results
                + json_numincrby_section_results
                + json_numincrby_event_results
                + json_get_result
                + hset_result
            )

            # When: Execute atomic reservation
            result = await executor.execute_atomic_reservation(
                event_id=123,
                section_id='A-1',
                booking_id='booking-123',
                bf_key='seats_bf:123:A-1',
                seats_to_reserve=seats,
                total_price=5000,
            )

            # Then: Should correctly handle multiple seats
            assert result['success'] is True
            assert len(result['reserved_seats']) == 5
            assert result['total_price'] == 5000

            # And: Stats should be parsed from JSON correctly
            # For 5 seats: 10 setbit + 4 JSON.NUMINCRBY (section x2 + event x2) + JSON.GET at idx 14
            assert result['subsection_stats'] == {
                'available': 95,
                'reserved': 5,
                'sold': 0,
                'total': 100,
            }
            assert result['event_stats'] == {
                'available': 495,
                'reserved': 5,
                'sold': 0,
                'total': 500,
            }

    @pytest.mark.asyncio
    async def test_execute_atomic_reservation_booking_metadata_format(self, executor, sample_seats):
        # Given: Mock Kvrocks client
        with patch.object(atomic_reservation_executor, KVROCKS_CLIENT_ATTR) as mock_kvrocks:
            mock_client = MagicMock()
            mock_pipeline = MagicMock()
            mock_kvrocks.get_client.return_value = mock_client
            mock_client.pipeline.return_value = mock_pipeline

            # Mock current event stats (for time tracking via JSON.GET)
            # execute_command is called for JSON.GET $.event_stats
            mock_client.execute_command = AsyncMock(
                return_value=b'[{"reserved":0,"sold":0,"available":500,"total":500}]'
            )

            # Standard mock results
            # ✨ NEW: 4 setbit + 4 JSON.NUMINCRBY + 1 JSON.GET + 1 HSET = 10 results
            mock_pipeline.execute = AsyncMock(
                return_value=[
                    1,
                    1,
                    1,
                    1,  # setbit (2 seats × 2 bits)
                    [98],
                    [2],  # JSON.NUMINCRBY (section stats)
                    [498],
                    [2],  # JSON.NUMINCRBY (event stats)
                    b'[{"sections":{"A-1":{"stats":{"available":98,"reserved":2,"sold":0,"total":100}}},"event_stats":{"available":498,"reserved":2,"sold":0,"total":500}}]',  # JSON.GET returns bytes
                    4,  # HSET (booking metadata)
                ]
            )

            # When: Execute atomic reservation
            await executor.execute_atomic_reservation(
                event_id=123,
                section_id='A-1',
                booking_id='booking-456',
                bf_key='seats_bf:123:A-1',
                seats_to_reserve=sample_seats,
                total_price=2000,
            )

            # Then: Should call hset with correct booking metadata
            mock_pipeline.hset.assert_called_once()
            call_args = mock_pipeline.hset.call_args

            # Verify booking key
            key_prefix = os.getenv('KVROCKS_KEY_PREFIX', '')
            assert call_args[0][0] == f'{key_prefix}booking:booking-456'

            # Verify mapping contains required fields
            mapping = call_args[1]['mapping']
            assert mapping['status'] == 'RESERVE_SUCCESS'
            assert mapping['reserved_seats'] == orjson.dumps(['A-1-1-1', 'A-1-1-2']).decode()
            assert mapping['total_price'] == '2000'
            assert 'config_key' in mapping

    @pytest.mark.asyncio
    async def test_execute_atomic_reservation_setbit_offsets(self, executor, sample_seats):
        # Given: Mock Kvrocks client
        with patch.object(atomic_reservation_executor, KVROCKS_CLIENT_ATTR) as mock_kvrocks:
            mock_client = MagicMock()
            mock_pipeline = MagicMock()
            mock_kvrocks.get_client.return_value = mock_client
            mock_client.pipeline.return_value = mock_pipeline

            # Mock current event stats (for time tracking via JSON.GET)
            # execute_command is called for JSON.GET $.event_stats
            mock_client.execute_command = AsyncMock(
                return_value=b'[{"reserved":0,"sold":0,"available":500,"total":500}]'
            )

            # ✨ NEW: 4 setbit + 4 JSON.NUMINCRBY + 1 JSON.GET + 1 HSET = 10 results
            mock_pipeline.execute = AsyncMock(
                return_value=[
                    1,
                    1,
                    1,
                    1,  # setbit (2 seats × 2 bits)
                    [98],
                    [2],  # JSON.NUMINCRBY (section stats)
                    [498],
                    [2],  # JSON.NUMINCRBY (event stats)
                    b'[{"sections":{"A-1":{"stats":{"available":98,"reserved":2,"sold":0,"total":100}}},"event_stats":{"available":498,"reserved":2,"sold":0,"total":500}}]',  # JSON.GET returns bytes
                    4,  # HSET (booking metadata)
                ]
            )

            # When: Execute atomic reservation
            await executor.execute_atomic_reservation(
                event_id=123,
                section_id='A-1',
                booking_id='booking-123',
                bf_key='seats_bf:123:A-1',
                seats_to_reserve=sample_seats,
                total_price=2000,
            )

            # Then: Setbit should be called with correct offsets
            # Seat 1 (index 0): offset = 0*2 = 0, 1
            # Seat 2 (index 1): offset = 1*2 = 2, 3
            setbit_calls = mock_pipeline.setbit.call_args_list
            assert len(setbit_calls) == 4

            # Seat 1
            assert setbit_calls[0][0] == ('seats_bf:123:A-1', 0, 0)  # bit0
            assert setbit_calls[1][0] == ('seats_bf:123:A-1', 1, 1)  # bit1

            # Seat 2
            assert setbit_calls[2][0] == ('seats_bf:123:A-1', 2, 0)  # bit0
            assert setbit_calls[3][0] == ('seats_bf:123:A-1', 3, 1)  # bit1
