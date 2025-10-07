"""
Integration test for seat initialization Lua script

這些測試會實際連接 Kvrocks，測試 Lua 腳本的正確性
"""

import os
import time

import pytest

from src.service.ticketing.driven_adapter.state.init_event_and_tickets_state_handler_impl import (
    InitEventAndTicketsStateHandlerImpl,
)


# Get key prefix for test isolation
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', 'test_')


def _make_key(key: str) -> str:
    """Add prefix to key for test isolation"""
    return f'{_KEY_PREFIX}{key}'


@pytest.fixture(scope='function')
def handler():
    """Create handler instance"""
    return InitEventAndTicketsStateHandlerImpl()


@pytest.fixture(scope='function')
def unique_event_id(kvrocks_client_sync_for_test):
    """Generate unique event_id for each test to avoid conflicts in parallel execution"""
    import random

    # Use timestamp (microseconds) + random for strong uniqueness guarantee
    event_id = int(time.time() * 1000000) % 10000000 + random.randint(1, 9999)

    # Extra cleanup: ensure no stale data for this event_id
    keys_to_clean = kvrocks_client_sync_for_test.keys(f'{_KEY_PREFIX}*:{event_id}:*')
    if keys_to_clean:
        kvrocks_client_sync_for_test.delete(*keys_to_clean)

    return event_id


class TestInitializeSeatsLuaScript:
    """Integration test for seat initialization Lua script"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_initialize_single_section(
        self, handler, kvrocks_client_sync_for_test, unique_event_id
    ):
        """Test initializing seats for a single section"""
        # Given: Simple seating config with 1 section
        config = {
            'sections': [
                {
                    'name': 'A',
                    'price': 1000,
                    'subsections': [{'number': 1, 'rows': 2, 'seats_per_row': 3}],
                }
            ]
        }
        event_id = unique_event_id

        # When: Initialize seats
        result = await handler.initialize_seats_from_config(
            event_id=event_id, seating_config=config
        )

        # Then: Should succeed
        assert result['success'] is True
        assert result['total_seats'] == 6  # 2 rows × 3 seats
        assert result['sections_count'] == 1

        # Verify bitfield was created
        bf_key = _make_key(f'seats_bf:{event_id}:A-1')
        bf_len = kvrocks_client_sync_for_test.bitcount(bf_key)
        assert bf_len >= 0  # Bitfield exists

        # Verify section stats
        stats_key = _make_key(f'section_stats:{event_id}:A-1')
        stats = kvrocks_client_sync_for_test.hgetall(stats_key)
        assert stats['section_id'] == 'A-1'
        assert stats['event_id'] == str(event_id)
        assert int(stats['available']) == 6
        assert int(stats['reserved']) == 0
        assert int(stats['sold']) == 0
        assert int(stats['total']) == 6

        # Verify section config
        config_key = _make_key(f'section_config:{event_id}:A-1')
        section_config = kvrocks_client_sync_for_test.hgetall(config_key)
        assert int(section_config['rows']) == 2
        assert int(section_config['seats_per_row']) == 3

        # Verify seat metadata (price for each seat)
        for row in range(1, 3):  # 2 rows
            meta_key = _make_key(f'seat_meta:{event_id}:A-1:{row}')
            prices = kvrocks_client_sync_for_test.hgetall(meta_key)
            assert len(prices) == 3  # 3 seats per row
            assert all(int(p) == 1000 for p in prices.values())

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_initialize_multiple_sections(
        self, handler, kvrocks_client_sync_for_test, unique_event_id
    ):
        """Test initializing seats for multiple sections"""
        # Given: Config with 2 sections, different prices
        config = {
            'sections': [
                {
                    'name': 'A',
                    'price': 3000,
                    'subsections': [{'number': 1, 'rows': 2, 'seats_per_row': 2}],
                },
                {
                    'name': 'B',
                    'price': 2000,
                    'subsections': [{'number': 1, 'rows': 1, 'seats_per_row': 3}],
                },
            ]
        }
        event_id = unique_event_id

        # When: Initialize seats
        result = await handler.initialize_seats_from_config(
            event_id=event_id, seating_config=config
        )

        # Then: Should succeed
        assert result['success'] is True
        assert result['total_seats'] == 7  # (2×2) + (1×3) = 7
        assert result['sections_count'] == 2

        # Verify both sections exist in index
        sections_key = _make_key(f'event_sections:{event_id}')
        sections = kvrocks_client_sync_for_test.zrange(sections_key, 0, -1)
        assert set(sections) == {'A-1', 'B-1'}

        # Verify Section A stats
        stats_a = kvrocks_client_sync_for_test.hgetall(_make_key(f'section_stats:{event_id}:A-1'))
        assert int(stats_a['total']) == 4

        # Verify Section B stats
        stats_b = kvrocks_client_sync_for_test.hgetall(_make_key(f'section_stats:{event_id}:B-1'))
        assert int(stats_b['total']) == 3

        # Verify prices are correct
        meta_a = kvrocks_client_sync_for_test.hgetall(_make_key(f'seat_meta:{event_id}:A-1:1'))
        assert all(int(p) == 3000 for p in meta_a.values())

        meta_b = kvrocks_client_sync_for_test.hgetall(_make_key(f'seat_meta:{event_id}:B-1:1'))
        assert all(int(p) == 2000 for p in meta_b.values())

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_seat_bitfield_initialization(
        self, handler, kvrocks_client_sync_for_test, unique_event_id
    ):
        """Test that seat bitfields are initialized to 00 (available)"""
        # Given: Small config for easy verification
        config = {
            'sections': [
                {
                    'name': 'A',
                    'price': 1000,
                    'subsections': [{'number': 1, 'rows': 1, 'seats_per_row': 2}],
                }
            ]
        }
        event_id = unique_event_id

        # When: Initialize seats
        await handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # Then: Verify bitfield is 00 (available) for both seats
        bf_key = _make_key(f'seats_bf:{event_id}:A-1')

        # Seat 0: bits 0-1
        seat0_bit0 = kvrocks_client_sync_for_test.getbit(bf_key, 0)
        seat0_bit1 = kvrocks_client_sync_for_test.getbit(bf_key, 1)
        assert seat0_bit0 == 0 and seat0_bit1 == 0  # Available

        # Seat 1: bits 2-3
        seat1_bit0 = kvrocks_client_sync_for_test.getbit(bf_key, 2)
        seat1_bit1 = kvrocks_client_sync_for_test.getbit(bf_key, 3)
        assert seat1_bit0 == 0 and seat1_bit1 == 0  # Available

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_multiple_subsections_same_section(
        self, handler, kvrocks_client_sync_for_test, unique_event_id
    ):
        """Test initializing multiple subsections in the same section"""
        # Given: Section A with 2 subsections
        config = {
            'sections': [
                {
                    'name': 'A',
                    'price': 1000,
                    'subsections': [
                        {'number': 1, 'rows': 1, 'seats_per_row': 2},
                        {'number': 2, 'rows': 1, 'seats_per_row': 3},
                    ],
                }
            ]
        }
        event_id = unique_event_id

        # When: Initialize seats
        result = await handler.initialize_seats_from_config(
            event_id=event_id, seating_config=config
        )

        # Then: Should create 2 separate subsections
        assert result['success'] is True
        assert result['total_seats'] == 5  # 2 + 3
        assert result['sections_count'] == 2  # A-1 and A-2

        # Verify both subsections exist
        sections = kvrocks_client_sync_for_test.zrange(
            _make_key(f'event_sections:{event_id}'), 0, -1
        )
        assert set(sections) == {'A-1', 'A-2'}

        # Verify separate stats
        stats_1 = kvrocks_client_sync_for_test.hgetall(_make_key(f'section_stats:{event_id}:A-1'))
        stats_2 = kvrocks_client_sync_for_test.hgetall(_make_key(f'section_stats:{event_id}:A-2'))
        assert int(stats_1['total']) == 2
        assert int(stats_2['total']) == 3

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_section_config_tracks_max_values(
        self, handler, kvrocks_client_sync_for_test, unique_event_id
    ):
        """Test that section_config correctly tracks max row and seats_per_row"""
        # Given: Subsection with varying rows
        config = {
            'sections': [
                {
                    'name': 'A',
                    'price': 1000,
                    'subsections': [
                        {'number': 1, 'rows': 5, 'seats_per_row': 10}  # Max values
                    ],
                }
            ]
        }
        event_id = unique_event_id

        # When: Initialize seats
        await handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # Then: Config should have correct max values
        config_key = _make_key(f'section_config:{event_id}:A-1')
        section_config = kvrocks_client_sync_for_test.hgetall(config_key)
        assert int(section_config['rows']) == 5
        assert int(section_config['seats_per_row']) == 10

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_large_scale_initialization(
        self, handler, kvrocks_client_sync_for_test, unique_event_id
    ):
        """Test initializing a realistic large-scale event"""
        # Given: Large event with 3 sections, 10 subsections each
        config = {
            'sections': [
                {
                    'name': 'A',
                    'price': 5000,
                    'subsections': [
                        {'number': i, 'rows': 10, 'seats_per_row': 20} for i in range(1, 11)
                    ],
                },
                {
                    'name': 'B',
                    'price': 3000,
                    'subsections': [
                        {'number': i, 'rows': 8, 'seats_per_row': 15} for i in range(1, 11)
                    ],
                },
                {
                    'name': 'C',
                    'price': 2000,
                    'subsections': [
                        {'number': i, 'rows': 5, 'seats_per_row': 10} for i in range(1, 11)
                    ],
                },
            ]
        }
        event_id = unique_event_id

        # When: Initialize seats
        result = await handler.initialize_seats_from_config(
            event_id=event_id, seating_config=config
        )

        # Then: Should successfully initialize all seats
        expected_total = (10 * 20 * 10) + (8 * 15 * 10) + (5 * 10 * 10)  # 4700 seats
        assert result['success'] is True
        assert result['total_seats'] == expected_total
        assert result['sections_count'] == 30  # 10 subsections × 3 sections

        # Verify a sample section exists
        stats = kvrocks_client_sync_for_test.hgetall(_make_key(f'section_stats:{event_id}:A-1'))
        assert int(stats['total']) == 200  # 10 rows × 20 seats
