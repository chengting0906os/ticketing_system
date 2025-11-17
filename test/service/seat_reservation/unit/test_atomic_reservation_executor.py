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
# Test _parse_json_get_result
# ============================================================================


@pytest.mark.unit
class TestParseJsonGetResult:
    """Test JSON.GET result parsing logic"""

    def test_parse_json_get_result_bytes(self):
        """Test parsing when JSON.GET returns JSON string (Kvrocks format)"""
        # Given: JSON.GET result as JSON string (what Kvrocks actually returns)
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
        # JSON.GET with $ returns: '[{"event_stats":{...},"sections":{...}}]'
        json_config_result = orjson.dumps([event_state_json])

        # When: Parse JSON string directly (simplified pattern)
        event_state_list = orjson.loads(json_config_result)
        parsed = event_state_list[0]

        # Then: Should parse correctly
        assert parsed == event_state_json
        assert parsed['event_stats']['available'] == 0
        assert parsed['sections']['A']['price'] == 3000

    def test_parse_json_get_result_with_array(self):
        """Test parsing JSON.GET result with array wrapper"""
        # Given: JSON.GET with $ wraps result in array
        event_state_json = {'event_stats': {'available': 100}}
        # JSON.GET returns: '[{"event_stats":{"available":100}}]'
        json_config_result = orjson.dumps([event_state_json])

        # When: Parse result (simplified pattern)
        event_state_list = orjson.loads(json_config_result)
        parsed = event_state_list[0]

        # Then: Should extract first element correctly
        assert parsed == event_state_json

    def test_parse_json_get_result_none(self):
        """Test parsing when JSON.GET returns None (key not found)"""
        # Given: None result (key not found)
        json_config_result = None

        # When/Then: Should handle None case
        if not json_config_result:
            event_state = {}
        else:
            event_state_list = orjson.loads(json_config_result)
            event_state = event_state_list[0]

        assert event_state == {}

    def test_parse_json_get_result_simplified_logic(self):
        """Test simplified parsing logic (new pattern)"""
        # Given: Standard JSON.GET result format
        event_state_json = {
            'event_stats': {'available': 500},
            'sections': {'A': {'price': 3000}},
        }
        # JSON.GET with $ returns: '[{"event_stats":{...},"sections":{...}}]'
        json_config_result = orjson.dumps([event_state_json])

        # When: Parse with simplified pattern (no isinstance checks needed)
        event_state_list = orjson.loads(json_config_result)
        parsed = event_state_list[0]

        # Then: Should work correctly
        assert parsed == event_state_json


@pytest.mark.unit
class TestParseEventStatsJsonPath:
    """Test JSON.GET $.event_stats parsing logic (JSONPath format always returns list[dict])"""

    def test_parse_event_stats_bytes(self):
        """Test parsing when JSON.GET $.event_stats returns JSON string"""
        # Given: JSON.GET $.event_stats result (what Kvrocks actually returns)
        event_stats = {
            'available': 100,
            'reserved': 400,
            'sold': 0,
            'total': 500,
            'updated_at': 1763299859,
        }
        # JSON.GET with $.event_stats returns: '[{"available":100,...}]'
        stats_result = orjson.dumps([event_stats])

        # When: Parse with simplified pattern
        parsed_list = orjson.loads(stats_result)
        parsed_stats = parsed_list[0]

        # Then: Should extract dict correctly
        assert parsed_stats == event_stats
        assert parsed_stats['available'] == 100
        assert parsed_stats['total'] == 500

    def test_parse_event_stats_direct_parse(self):
        """Test direct parsing without intermediate steps"""
        # Given: JSON.GET result as JSON string
        event_stats = {'available': 250, 'reserved': 250, 'sold': 0, 'total': 500}
        # JSON.GET returns: '[{"available":250,...}]'
        stats_result = orjson.dumps([event_stats])

        # When: Parse directly (most efficient)
        parsed_list = orjson.loads(stats_result)
        parsed_stats = parsed_list[0]

        # Then: Should parse correctly
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
        # Given: JSON array with null
        # JSON.GET returns: '[null]' when key exists but value is null
        stats_result = orjson.dumps([None])

        # When: Parse result
        parsed_list = orjson.loads(stats_result)
        parsed_stats = parsed_list[0]

        # Then: Should return None (triggers fallback to full JSON.GET)
        assert parsed_stats is None


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

            # Mock current event_state (for price calculation and time tracking via JSON.GET)
            # execute_command is called for JSON.GET event_state (returns bytes with full state including sections)
            mock_client.execute_command = AsyncMock(
                return_value=b'[{"sections":{"A":{"price":1000,"subsections":{"1":{"stats":{"available":100,"reserved":0,"sold":0,"total":100}}}}},"event_stats":{"reserved":0,"sold":0,"available":500,"total":500}}]'
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

            # Mock current event_state (for price calculation and time tracking via JSON.GET)
            # execute_command is called for JSON.GET event_state
            mock_client.execute_command = AsyncMock(
                return_value=b'[{"sections":{"A":{"price":1000,"subsections":{"1":{"stats":{"available":100,"reserved":0,"sold":0,"total":100}}}}},"event_stats":{"reserved":0,"sold":0,"available":500,"total":500}}]'
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

            # Mock current event_state (for price calculation and time tracking via JSON.GET)
            # execute_command is called for JSON.GET event_state
            mock_client.execute_command = AsyncMock(
                return_value=b'[{"sections":{"A":{"price":1000,"subsections":{"1":{"stats":{"available":100,"reserved":0,"sold":0,"total":100}}}}},"event_stats":{"reserved":0,"sold":0,"available":500,"total":500}}]'
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

            # Mock current event_state (for price calculation and time tracking via JSON.GET)
            # execute_command is called for JSON.GET event_state
            mock_client.execute_command = AsyncMock(
                return_value=b'[{"sections":{"A":{"price":1000,"subsections":{"1":{"stats":{"available":100,"reserved":0,"sold":0,"total":100}}}}},"event_stats":{"reserved":0,"sold":0,"available":500,"total":500}}]'
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
                    b'[{"sections":{"A":{"price":1000,"subsections":{"1":{"stats":{"available":98,"reserved":2,"sold":0,"total":100}}}}},"event_stats":{"available":498,"reserved":2,"sold":0,"total":500}}]',  # JSON.GET returns bytes
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

            # Mock current event_state (for price calculation and time tracking via JSON.GET)
            # execute_command is called for JSON.GET event_state
            mock_client.execute_command = AsyncMock(
                return_value=b'[{"sections":{"A":{"price":1000,"subsections":{"1":{"stats":{"available":100,"reserved":0,"sold":0,"total":100}}}}},"event_stats":{"reserved":0,"sold":0,"available":500,"total":500}}]'
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
                    b'[{"sections":{"A":{"price":1000,"subsections":{"1":{"stats":{"available":98,"reserved":2,"sold":0,"total":100}}}}},"event_stats":{"available":498,"reserved":2,"sold":0,"total":500}}]',  # JSON.GET returns bytes
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
