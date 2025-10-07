"""
Integration test for reserve seats Lua script

測試座位預訂的 Lua 腳本，包含 Check-and-Set 模式和統計更新
"""

import os

import pytest

from src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl import (
    SeatStateCommandHandlerImpl,
)
from src.service.ticketing.driven_adapter.state.init_event_and_tickets_state_handler_impl import (
    InitEventAndTicketsStateHandlerImpl,
)


# Get key prefix for test isolation
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', 'test_')


def _make_key(key: str) -> str:
    """Add prefix to key for test isolation"""
    return f'{_KEY_PREFIX}{key}'


@pytest.fixture
def seat_handler():
    """Create seat state command handler"""
    return SeatStateCommandHandlerImpl()


@pytest.fixture
def init_handler():
    """Create seat initialization handler"""
    return InitEventAndTicketsStateHandlerImpl()


class TestReserveSeatsLuaScript:
    """Integration test for reserve seats Lua script"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reserve_single_seat_success(
        self, kvrocks_client_sync_for_test, seat_handler, init_handler
    ):
        """Test reserving a single available seat"""
        # Given: Initialize seats
        config = {
            'sections': [
                {
                    'name': 'A',
                    'price': 1000,
                    'subsections': [{'number': 1, 'rows': 1, 'seats_per_row': 3}],
                }
            ]
        }
        event_id = 1
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # When: Reserve one seat
        seat_ids = ['A-1-1-1']
        results = await seat_handler.reserve_seats(
            seat_ids=seat_ids, booking_id=100, buyer_id=1, event_id=event_id
        )

        # Then: Should succeed
        assert results['A-1-1-1'] is True

        # Verify seat status is RESERVED (01)
        bf_key = _make_key(f'seats_bf:{event_id}:A-1')
        bit0 = kvrocks_client_sync_for_test.getbit(bf_key, 0)
        bit1 = kvrocks_client_sync_for_test.getbit(bf_key, 1)
        assert (bit0, bit1) == (1, 0)  # RESERVED

        # Verify stats updated
        stats_key = _make_key(f'section_stats:{event_id}:A-1')
        stats = kvrocks_client_sync_for_test.hgetall(stats_key)
        assert int(stats['available']) == 2  # 3 - 1
        assert int(stats['reserved']) == 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reserve_multiple_seats_atomically(
        self, kvrocks_client_sync_for_test, seat_handler, init_handler
    ):
        """Test reserving multiple seats in one atomic operation"""
        # Given: Initialize seats
        config = {
            'sections': [
                {
                    'name': 'A',
                    'price': 1000,
                    'subsections': [{'number': 1, 'rows': 2, 'seats_per_row': 3}],
                }
            ]
        }
        event_id = 2
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # When: Reserve 3 seats
        seat_ids = ['A-1-1-1', 'A-1-1-2', 'A-1-2-1']
        results = await seat_handler.reserve_seats(
            seat_ids=seat_ids, booking_id=101, buyer_id=2, event_id=event_id
        )

        # Then: All should succeed
        assert all(results.values())
        assert len(results) == 3

        # Verify stats
        stats_key = _make_key(f'section_stats:{event_id}:A-1')
        stats = kvrocks_client_sync_for_test.hgetall(stats_key)
        assert int(stats['available']) == 3  # 6 - 3
        assert int(stats['reserved']) == 3

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reserve_already_reserved_seat_fails(
        self, kvrocks_client_sync_for_test, seat_handler, init_handler
    ):
        """Test Check-and-Set: cannot reserve already reserved seat"""
        # Given: Initialize and reserve a seat
        config = {
            'sections': [
                {
                    'name': 'A',
                    'price': 1000,
                    'subsections': [{'number': 1, 'rows': 1, 'seats_per_row': 2}],
                }
            ]
        }
        event_id = 3
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # Reserve seat A-1-1-1
        await seat_handler.reserve_seats(
            seat_ids=['A-1-1-1'], booking_id=102, buyer_id=3, event_id=event_id
        )

        # When: Try to reserve the same seat again
        results = await seat_handler.reserve_seats(
            seat_ids=['A-1-1-1'], booking_id=103, buyer_id=4, event_id=event_id
        )

        # Then: Should fail
        assert results['A-1-1-1'] is False

        # Stats should not change
        stats_key = _make_key(f'section_stats:{event_id}:A-1')
        stats = kvrocks_client_sync_for_test.hgetall(stats_key)
        assert int(stats['available']) == 1  # Still 1
        assert int(stats['reserved']) == 1  # Still 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_partial_reservation_failure(
        self, kvrocks_client_sync_for_test, seat_handler, init_handler
    ):
        """Test partial failure: some seats reserved, some already taken"""
        # Given: Initialize seats and reserve one
        config = {
            'sections': [
                {
                    'name': 'A',
                    'price': 1000,
                    'subsections': [{'number': 1, 'rows': 1, 'seats_per_row': 3}],
                }
            ]
        }
        event_id = 4
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # Reserve seat A-1-1-2
        await seat_handler.reserve_seats(
            seat_ids=['A-1-1-2'], booking_id=104, buyer_id=5, event_id=event_id
        )

        # When: Try to reserve 3 seats including the reserved one
        seat_ids = ['A-1-1-1', 'A-1-1-2', 'A-1-1-3']
        results = await seat_handler.reserve_seats(
            seat_ids=seat_ids, booking_id=105, buyer_id=6, event_id=event_id
        )

        # Then: Only available seats should be reserved
        assert results['A-1-1-1'] is True
        assert results['A-1-1-2'] is False  # Already reserved
        assert results['A-1-1-3'] is True

        # Stats should reflect 2 new reservations
        stats_key = _make_key(f'section_stats:{event_id}:A-1')
        stats = kvrocks_client_sync_for_test.hgetall(stats_key)
        assert int(stats['available']) == 0  # All taken
        assert int(stats['reserved']) == 3  # 1 (before) + 2 (new)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reserve_seats_updates_timestamp(
        self, kvrocks_client_sync_for_test, seat_handler, init_handler
    ):
        """Test that reservation updates the timestamp"""
        # Given: Initialize seats
        config = {
            'sections': [
                {
                    'name': 'A',
                    'price': 1000,
                    'subsections': [{'number': 1, 'rows': 1, 'seats_per_row': 1}],
                }
            ]
        }
        event_id = 5
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # Get initial timestamp
        stats_key = _make_key(f'section_stats:{event_id}:A-1')
        initial_stats = kvrocks_client_sync_for_test.hgetall(stats_key)
        initial_timestamp = initial_stats['updated_at']

        # When: Reserve a seat
        await seat_handler.reserve_seats(
            seat_ids=['A-1-1-1'], booking_id=106, buyer_id=7, event_id=event_id
        )

        # Then: Timestamp should be updated
        updated_stats = kvrocks_client_sync_for_test.hgetall(stats_key)
        updated_timestamp = updated_stats['updated_at']
        assert updated_timestamp >= initial_timestamp

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reserve_seats_across_multiple_sections(
        self, kvrocks_client_sync_for_test, seat_handler, init_handler
    ):
        """Test reserving seats from different sections atomically"""
        # Given: Initialize multiple sections
        config = {
            'sections': [
                {
                    'name': 'A',
                    'price': 3000,
                    'subsections': [{'number': 1, 'rows': 1, 'seats_per_row': 2}],
                },
                {
                    'name': 'B',
                    'price': 2000,
                    'subsections': [{'number': 1, 'rows': 1, 'seats_per_row': 2}],
                },
            ]
        }
        event_id = 6
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # When: Reserve seats from both sections
        seat_ids = ['A-1-1-1', 'B-1-1-1']
        results = await seat_handler.reserve_seats(
            seat_ids=seat_ids, booking_id=107, buyer_id=8, event_id=event_id
        )

        # Then: Both should succeed
        assert all(results.values())

        # Verify stats for both sections
        stats_a = kvrocks_client_sync_for_test.hgetall(_make_key(f'section_stats:{event_id}:A-1'))
        stats_b = kvrocks_client_sync_for_test.hgetall(_make_key(f'section_stats:{event_id}:B-1'))
        assert int(stats_a['reserved']) == 1
        assert int(stats_b['reserved']) == 1
