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


@pytest.fixture
def sample_seat_prices():
    return {
        'A-1-1-1': 1000,
        'A-1-1-2': 1000,
    }


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
# Test fetch_seat_prices
# ============================================================================


@pytest.mark.unit
class TestFetchSeatPrices:
    @pytest.mark.asyncio
    async def test_fetch_seat_prices_success(self, executor, sample_seats):
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
            config_json = orjson.dumps(event_state).decode()

            # Mock JSON.GET command (native JSON support)
            mock_client.execute_command = AsyncMock(return_value=[config_json])

            # When: Fetch seat prices
            seat_prices, total_price = await executor.fetch_seat_prices(
                event_id=123,
                section_id='A-1',
                seats_to_reserve=sample_seats,
            )

            # Then: Should return correct prices (same price for all seats)
            assert seat_prices == {
                'A-1-1-1': 1000,
                'A-1-1-2': 1000,
            }
            assert total_price == 2000

            # And: Should call JSON.GET once
            mock_client.execute_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_seat_prices_missing_prices(self, executor):
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
            config_json = orjson.dumps(event_state).decode()
            mock_client.execute_command = AsyncMock(return_value=[config_json])

            # When: Fetch seat prices for missing section
            seat_prices, total_price = await executor.fetch_seat_prices(
                event_id=123,
                section_id='A-1',  # Not in config
                seats_to_reserve=seats,
            )

            # Then: Missing prices should default to 0
            assert seat_prices == {
                'A-1-1-1': 0,
                'A-1-1-2': 0,
                'A-1-1-3': 0,
            }
            assert total_price == 0

    @pytest.mark.asyncio
    async def test_fetch_seat_prices_different_prices(self, executor):
        # Given: Multiple sections with different prices
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
            config_json = orjson.dumps(event_state).decode()
            mock_client.execute_command = AsyncMock(return_value=[config_json])

            # When: Fetch seat prices for A-1
            seat_prices, total_price = await executor.fetch_seat_prices(
                event_id=123,
                section_id='A-1',
                seats_to_reserve=seats_a1,
            )

            # Then: All seats in same section have same price
            assert seat_prices == {
                'A-1-1-1': 1000,
                'A-1-1-2': 1000,
            }
            assert total_price == 2000


# ============================================================================
# Test execute_atomic_reservation
# ============================================================================


@pytest.mark.unit
class TestExecuteAtomicReservation:
    @pytest.mark.asyncio
    async def test_execute_atomic_reservation_success(
        self, executor, sample_seats, sample_seat_prices
    ):
        # Given: Mock Kvrocks client and pipeline
        with patch.object(atomic_reservation_executor, KVROCKS_CLIENT_ATTR) as mock_kvrocks:
            mock_client = MagicMock()
            mock_pipeline = MagicMock()
            mock_kvrocks.get_client.return_value = mock_client
            mock_client.pipeline.return_value = mock_pipeline

            # Mock current event stats (for time tracking via JSON.GET)
            # execute_command is called for JSON.GET $.event_stats
            mock_client.execute_command = AsyncMock(
                return_value=['{"reserved":0,"sold":0,"available":500,"total":500}']
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
                    # JSON.GET result (complete event_state with hierarchical structure)
                    [
                        '{"sections":{"A":{"price":1000,"subsections":{"1":{"stats":{"available":98,"reserved":2,"sold":0,"total":100}}}}},"event_stats":{"available":498,"reserved":2,"sold":0,"total":500}}'
                    ],
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
                seat_prices=sample_seat_prices,
                total_price=2000,
            )

            # Then: Should return success result
            assert result['success'] is True
            assert result['reserved_seats'] == ['A-1-1-1', 'A-1-1-2']
            assert result['seat_prices'] == sample_seat_prices
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
        seat_prices = {'A-1-1-1': 1000}

        with patch.object(atomic_reservation_executor, KVROCKS_CLIENT_ATTR) as mock_kvrocks:
            mock_client = MagicMock()
            mock_pipeline = MagicMock()
            mock_kvrocks.get_client.return_value = mock_client
            mock_client.pipeline.return_value = mock_pipeline

            # Mock current event stats (for time tracking via JSON.GET)
            # execute_command is called for JSON.GET $.event_stats
            mock_client.execute_command = AsyncMock(
                return_value=['{"reserved":0,"sold":0,"available":500,"total":500}']
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
                    # JSON.GET result (complete event_state with hierarchical structure)
                    [
                        '{"sections":{"A":{"price":1000,"subsections":{"1":{"stats":{"available":99,"reserved":1,"sold":0,"total":100}}}}},"event_stats":{"available":499,"reserved":1,"sold":0,"total":500}}'
                    ],
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
                seat_prices=seat_prices,
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
        seat_prices = {seat_id: 1000 for _, _, _, seat_id in seats}

        with patch.object(atomic_reservation_executor, KVROCKS_CLIENT_ATTR) as mock_kvrocks:
            mock_client = MagicMock()
            mock_pipeline = MagicMock()
            mock_kvrocks.get_client.return_value = mock_client
            mock_client.pipeline.return_value = mock_pipeline

            # Mock current event stats (for time tracking via JSON.GET)
            # execute_command is called for JSON.GET $.event_stats
            mock_client.execute_command = AsyncMock(
                return_value=['{"reserved":0,"sold":0,"available":500,"total":500}']
            )

            # Mock pipeline results for 5 seats
            # ✨ NEW: 10 setbit + 4 JSON.NUMINCRBY + 1 JSON.GET + 1 HSET = 16 results
            setbit_results = [1] * 10  # 5 seats × 2 bits
            json_numincrby_section_results = [[95], [5]]  # section stats (returns new values)
            json_numincrby_event_results = [[495], [5]]  # event stats
            json_get_result = [
                [
                    '{"sections":{"A":{"price":1000,"subsections":{"1":{"stats":{"available":95,"reserved":5,"sold":0,"total":100}}}}},"event_stats":{"available":495,"reserved":5,"sold":0,"total":500}}'
                ]
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
                seat_prices=seat_prices,
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
    async def test_execute_atomic_reservation_booking_metadata_format(
        self, executor, sample_seats, sample_seat_prices
    ):
        # Given: Mock Kvrocks client
        with patch.object(atomic_reservation_executor, KVROCKS_CLIENT_ATTR) as mock_kvrocks:
            mock_client = MagicMock()
            mock_pipeline = MagicMock()
            mock_kvrocks.get_client.return_value = mock_client
            mock_client.pipeline.return_value = mock_pipeline

            # Mock current event stats (for time tracking via JSON.GET)
            # execute_command is called for JSON.GET $.event_stats
            mock_client.execute_command = AsyncMock(
                return_value=['{"reserved":0,"sold":0,"available":500,"total":500}']
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
                    [
                        '{"sections":{"A-1":{"stats":{"available":98,"reserved":2,"sold":0,"total":100}}},"event_stats":{"available":498,"reserved":2,"sold":0,"total":500}}'
                    ],  # JSON.GET (complete event_state)
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
                seat_prices=sample_seat_prices,
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
            assert (
                mapping['seat_prices'] == orjson.dumps({'A-1-1-1': 1000, 'A-1-1-2': 1000}).decode()
            )
            assert mapping['total_price'] == '2000'
            # ✨ CHANGED: 'stats_key' → 'config_key' (now using event_state JSON instead of section_stats Hash)
            assert 'config_key' in mapping
            # ✨ REMOVED: event_stats_key (stats now in unified event_state JSON)

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
                return_value=['{"reserved":0,"sold":0,"available":500,"total":500}']
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
                    [
                        '{"sections":{"A-1":{"stats":{"available":98,"reserved":2,"sold":0,"total":100}}},"event_stats":{"available":498,"reserved":2,"sold":0,"total":500}}'
                    ],  # JSON.GET (complete event_state)
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
                seat_prices={'A-1-1-1': 1000, 'A-1-1-2': 1000},
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
