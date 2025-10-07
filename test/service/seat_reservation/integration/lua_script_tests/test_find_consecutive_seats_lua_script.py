"""
Integration test for find and reserve consecutive seats Lua script

測試 Lua 自動找出連續座位並預訂的功能
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


class TestFindConsecutiveSeatsLuaScript:
    """Integration test for find and reserve consecutive seats Lua script"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_and_reserve_consecutive_seats_in_single_row(
        self, kvrocks_client_sync_for_test, seat_handler, init_handler
    ):
        """Test finding and reserving consecutive seats in a single row"""
        # Given: Initialize seats with 1 row, 5 seats
        config = {
            'sections': [
                {
                    'name': 'A',
                    'price': 1000,
                    'subsections': [{'number': 1, 'rows': 1, 'seats_per_row': 5}],
                }
            ]
        }
        event_id = 1
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # When: Request 3 consecutive seats (best_available mode)
        result = await seat_handler.find_and_reserve_consecutive_seats(
            event_id=event_id,
            section='A',
            subsection=1,
            quantity=3,
            booking_id=100,
            buyer_id=1,
        )

        # Then: Should successfully reserve 3 consecutive seats
        assert result['success'] is True
        assert len(result['reserved_seats']) == 3

        # Verify they are consecutive in same row
        seat_ids = result['reserved_seats']
        assert seat_ids == ['A-1-1-1', 'A-1-1-2', 'A-1-1-3']

        # Verify stats updated
        stats_key = _make_key(f'section_stats:{event_id}:A-1')
        stats = kvrocks_client_sync_for_test.hgetall(stats_key)
        assert int(stats['available']) == 2  # 5 - 3
        assert int(stats['reserved']) == 3

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_across_multiple_rows(
        self, kvrocks_client_sync_for_test, seat_handler, init_handler
    ):
        """Test finding consecutive seats when first row doesn't have enough"""
        # Given: Initialize seats with 2 rows, 3 seats per row
        # Reserve 2 seats in first row, leaving only 1 available
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

        # Reserve 2 seats in first row
        await seat_handler.reserve_seats(
            seat_ids=['A-1-1-1', 'A-1-1-2'], booking_id=99, buyer_id=99, event_id=event_id
        )

        # When: Request 2 consecutive seats
        result = await seat_handler.find_and_reserve_consecutive_seats(
            event_id=event_id,
            section='A',
            subsection=1,
            quantity=2,
            booking_id=100,
            buyer_id=1,
        )

        # Then: Should find consecutive seats in second row
        assert result['success'] is True
        seat_ids = result['reserved_seats']
        assert seat_ids == ['A-1-2-1', 'A-1-2-2']  # Row 2, seats 1-2

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_no_consecutive_seats_available(
        self, kvrocks_client_sync_for_test, seat_handler, init_handler
    ):
        """Test when no consecutive seats are available"""
        # Given: Initialize 1 row with 3 seats, reserve middle seat
        config = {
            'sections': [
                {
                    'name': 'A',
                    'price': 1000,
                    'subsections': [{'number': 1, 'rows': 1, 'seats_per_row': 3}],
                }
            ]
        }
        event_id = 3
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # Reserve middle seat to break continuity
        await seat_handler.reserve_seats(
            seat_ids=['A-1-1-2'], booking_id=99, buyer_id=99, event_id=event_id
        )

        # When: Request 2 consecutive seats (but only [1] and [3] available)
        result = await seat_handler.find_and_reserve_consecutive_seats(
            event_id=event_id,
            section='A',
            subsection=1,
            quantity=2,
            booking_id=100,
            buyer_id=1,
        )

        # Then: Should fail
        assert result['success'] is False
        assert 'no consecutive seats' in result['error_message'].lower()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_best_position_for_consecutive_seats(
        self, kvrocks_client_sync_for_test, seat_handler, init_handler
    ):
        """Test that it finds the best (earliest) position for consecutive seats"""
        # Given: Multiple rows with available seats
        config = {
            'sections': [
                {
                    'name': 'A',
                    'price': 1000,
                    'subsections': [{'number': 1, 'rows': 3, 'seats_per_row': 4}],
                }
            ]
        }
        event_id = 4
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # Reserve some seats to create gaps
        await seat_handler.reserve_seats(
            seat_ids=['A-1-1-1', 'A-1-1-2'],  # Row 1: XX--
            booking_id=98,
            buyer_id=98,
            event_id=event_id,
        )

        # When: Request 2 consecutive seats
        result = await seat_handler.find_and_reserve_consecutive_seats(
            event_id=event_id,
            section='A',
            subsection=1,
            quantity=2,
            booking_id=100,
            buyer_id=1,
        )

        # Then: Should choose row 1 seats 3-4 (earliest available consecutive pair)
        assert result['success'] is True
        assert result['reserved_seats'] == ['A-1-1-3', 'A-1-1-4']
