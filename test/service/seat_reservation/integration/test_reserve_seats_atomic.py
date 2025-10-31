"""
Integration test for reserve_seats_atomic using Pipeline

Tests the unified seat reservation implementation supporting two modes:
1. manual mode - Reserve specific seat IDs
2. best_available mode - Automatically find and reserve consecutive seats
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


@pytest.fixture(scope='function')
def unique_event_id(kvrocks_client_sync_for_test):
    """Generate unique event_id for each test to avoid conflicts in parallel execution"""
    import random
    import time

    # Use timestamp (microseconds) + random for strong uniqueness guarantee
    event_id = int(time.time() * 1000000) % 10000000 + random.randint(1, 9999)

    # Extra cleanup: ensure no stale data for this event_id
    keys_to_clean = kvrocks_client_sync_for_test.keys(f'{_KEY_PREFIX}*:{event_id}:*')
    if keys_to_clean:
        kvrocks_client_sync_for_test.delete(*keys_to_clean)

    return event_id


class TestReserveSeatsAtomicManualMode:
    """Test reserve_seats_atomic() - Manual Mode (manual seat selection)"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reserve_single_seat_success(
        self, kvrocks_client_sync_for_test, seat_handler, init_handler, unique_event_id
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
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # When: Reserve one seat using manual mode
        result = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=100,
            buyer_id=1,
            mode='manual',
            section='A',
            subsection=1,
            seat_ids=['1-1'],
        )

        # Then: Should succeed
        assert result['success'] is True
        assert result['reserved_seats'] == ['A-1-1-1']

        # Verify seat status is RESERVED (01 binary)
        # Bit encoding: status = bit0*2 + bit1
        # RESERVED=1: bit0=0, bit1=1 → 0*2 + 1 = 1
        bf_key = _make_key(f'seats_bf:{event_id}:A-1')
        bit0 = kvrocks_client_sync_for_test.getbit(bf_key, 0)
        bit1 = kvrocks_client_sync_for_test.getbit(bf_key, 1)
        assert (bit0, bit1) == (0, 1)  # RESERVED
        assert bit0 * 2 + bit1 == 1  # status value = 1 (RESERVED)

        # Verify stats updated
        stats_key = _make_key(f'section_stats:{event_id}:A-1')
        stats = kvrocks_client_sync_for_test.hgetall(stats_key)
        assert int(stats['available']) == 2  # 3 - 1
        assert int(stats['reserved']) == 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reserve_multiple_seats_atomically(
        self, kvrocks_client_sync_for_test, seat_handler, init_handler, unique_event_id
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
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # When: Reserve 3 seats using manual mode
        result = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=101,
            buyer_id=2,
            mode='manual',
            section='A',
            subsection=1,
            seat_ids=['1-1', '1-2', '2-1'],
        )

        # Then: Should succeed
        assert result['success'] is True
        assert len(result['reserved_seats']) == 3
        # All reserved seats should be in full format
        expected_seats = ['A-1-1-1', 'A-1-1-2', 'A-1-2-1']
        assert sorted(result['reserved_seats']) == sorted(expected_seats)

        # Verify stats
        stats_key = _make_key(f'section_stats:{event_id}:A-1')
        stats = kvrocks_client_sync_for_test.hgetall(stats_key)
        assert int(stats['available']) == 3  # 6 - 3
        assert int(stats['reserved']) == 3

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reserve_already_reserved_seat_fails(
        self, kvrocks_client_sync_for_test, seat_handler, init_handler, unique_event_id
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
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # Reserve seat A-1-1-1
        await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=102,
            buyer_id=3,
            mode='manual',
            section='A',
            subsection=1,
            seat_ids=['1-1'],
        )

        # When: Try to reserve the same seat again
        result = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=103,
            buyer_id=4,
            mode='manual',
            section='A',
            subsection=1,
            seat_ids=['1-1'],
        )

        # Then: Should fail
        assert result['success'] is False

        # Stats should not change
        stats_key = _make_key(f'section_stats:{event_id}:A-1')
        stats = kvrocks_client_sync_for_test.hgetall(stats_key)
        assert int(stats['available']) == 1  # Still 1
        assert int(stats['reserved']) == 1  # Still 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_partial_reservation_failure(
        self, kvrocks_client_sync_for_test, seat_handler, init_handler, unique_event_id
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
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # Reserve seat A-1-1-2
        await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=104,
            buyer_id=5,
            mode='manual',
            section='A',
            subsection=1,
            seat_ids=['1-2'],
        )

        # When: Try to reserve 3 seats including the reserved one
        result = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=105,
            buyer_id=6,
            mode='manual',
            section='A',
            subsection=1,
            seat_ids=['1-1', '1-2', '1-3'],
        )

        # Then: Should fail (manual mode requires ALL seats to be available)
        assert result['success'] is False

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reserve_seats_updates_timestamp(
        self, kvrocks_client_sync_for_test, seat_handler, init_handler, unique_event_id
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
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # Get initial timestamp
        stats_key = _make_key(f'section_stats:{event_id}:A-1')
        initial_stats = kvrocks_client_sync_for_test.hgetall(stats_key)
        initial_timestamp = initial_stats['updated_at']

        # When: Reserve a seat
        await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=106,
            buyer_id=7,
            mode='manual',
            section='A',
            subsection=1,
            seat_ids=['1-1'],
        )

        # Then: Timestamp should be updated
        updated_stats = kvrocks_client_sync_for_test.hgetall(stats_key)
        updated_timestamp = updated_stats['updated_at']
        assert updated_timestamp >= initial_timestamp

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reserve_seats_across_multiple_sections(
        self, kvrocks_client_sync_for_test, seat_handler, init_handler, unique_event_id
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
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # When: Reserve seats from both sections (need separate calls for different sections)
        result_a = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=107,
            buyer_id=8,
            mode='manual',
            section='A',
            subsection=1,
            seat_ids=['1-1'],
        )

        result_b = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=107,
            buyer_id=8,
            mode='manual',
            section='B',
            subsection=1,
            seat_ids=['1-1'],
        )

        # Combine results for assertion
        result = {
            'success': result_a['success'] and result_b['success'],
            'reserved_seats': result_a['reserved_seats'] + result_b['reserved_seats'],
        }

        # Then: Should succeed
        assert result['success'] is True

        # Verify stats for both sections
        stats_a = kvrocks_client_sync_for_test.hgetall(_make_key(f'section_stats:{event_id}:A-1'))
        stats_b = kvrocks_client_sync_for_test.hgetall(_make_key(f'section_stats:{event_id}:B-1'))
        assert int(stats_a['reserved']) == 1
        assert int(stats_b['reserved']) == 1


class TestReserveSeatsAtomicBestAvailableMode:
    """Test reserve_seats_atomic() - Best Available Mode (auto-find consecutive seats)"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_and_reserve_consecutive_seats_in_single_row(
        self, kvrocks_client_sync_for_test, seat_handler, init_handler, unique_event_id
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
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # When: Request 3 consecutive seats (best_available mode)
        result = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=100,
            buyer_id=1,
            mode='best_available',
            section='A',
            subsection=1,
            quantity=3,
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
        self, kvrocks_client_sync_for_test, seat_handler, init_handler, unique_event_id
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
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # Reserve 2 seats in first row
        await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=99,
            buyer_id=99,
            mode='manual',
            section='A',
            subsection=1,
            seat_ids=['1-1', '1-2'],
        )

        # When: Request 2 consecutive seats
        result = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=100,
            buyer_id=1,
            mode='best_available',
            section='A',
            subsection=1,
            quantity=2,
        )

        # Then: Should find consecutive seats in second row
        assert result['success'] is True
        seat_ids = result['reserved_seats']
        assert seat_ids == ['A-1-2-1', 'A-1-2-2']  # Row 2, seats 1-2

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_no_consecutive_seats_available(
        self, kvrocks_client_sync_for_test, seat_handler, init_handler, unique_event_id
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
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # Reserve middle seat to break continuity
        await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=99,
            buyer_id=99,
            mode='manual',
            section='A',
            subsection=1,
            seat_ids=['1-2'],
        )

        # When: Request 2 consecutive seats (but only [1] and [3] available)
        result = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=100,
            buyer_id=1,
            mode='best_available',
            section='A',
            subsection=1,
            quantity=2,
        )

        # Then: Should fail
        assert result['success'] is False
        assert 'consecutive seats available' in result['error_message'].lower()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_best_position_for_consecutive_seats(
        self, kvrocks_client_sync_for_test, seat_handler, init_handler, unique_event_id
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
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # Reserve some seats to create gaps
        await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=98,
            buyer_id=98,
            mode='manual',
            section='A',
            subsection=1,
            seat_ids=['1-1', '1-2'],  # Row 1: XX--
        )

        # When: Request 2 consecutive seats
        result = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=100,
            buyer_id=1,
            mode='best_available',
            section='A',
            subsection=1,
            quantity=2,
        )

        # Then: Should choose row 1 seats 3-4 (earliest available consecutive pair)
        assert result['success'] is True
        assert result['reserved_seats'] == ['A-1-1-3', 'A-1-1-4']

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reserved_status_not_sold(
        self, kvrocks_client_sync_for_test, seat_handler, init_handler, unique_event_id
    ):
        """
        Test that reserved seats have correct status (RESERVED not SOLD)

        This test specifically validates the bug fix where reserved seats
        were incorrectly showing as 'sold' instead of 'reserved'.

        Bug: Bitfield encoding was setting bit0=1, bit1=0 which resulted in
             status = 1*2 + 0 = 2 (SOLD) instead of 1 (RESERVED)
        Fix: Changed to bit0=0, bit1=1 which gives status = 0*2 + 1 = 1 (RESERVED)
        """
        # Given: Initialize seats
        config = {
            'sections': [
                {
                    'name': 'A',
                    'price': 3000,
                    'subsections': [{'number': 1, 'rows': 2, 'seats_per_row': 5}],
                }
            ]
        }
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # When: Reserve 3 seats using manual mode
        result = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=100,
            buyer_id=1,
            mode='manual',
            section='A',
            subsection=1,
            seat_ids=['1-1', '1-2', '2-1'],
        )

        # Then: Reservation should succeed
        assert result['success'] is True
        assert len(result['reserved_seats']) == 3

        # Verify each reserved seat has correct bitfield encoding
        bf_key = _make_key(f'seats_bf:{event_id}:A-1')

        # Check seat A-1-1-1 (index 0)
        bit0_s1 = kvrocks_client_sync_for_test.getbit(bf_key, 0)
        bit1_s1 = kvrocks_client_sync_for_test.getbit(bf_key, 1)
        status_s1 = bit0_s1 * 2 + bit1_s1
        assert (bit0_s1, bit1_s1) == (0, 1), 'Seat 1 should have bit0=0, bit1=1'
        assert status_s1 == 1, f'Seat 1 should have status=1 (RESERVED), got {status_s1}'

        # Check seat A-1-1-2 (index 1)
        bit0_s2 = kvrocks_client_sync_for_test.getbit(bf_key, 2)
        bit1_s2 = kvrocks_client_sync_for_test.getbit(bf_key, 3)
        status_s2 = bit0_s2 * 2 + bit1_s2
        assert (bit0_s2, bit1_s2) == (0, 1), 'Seat 2 should have bit0=0, bit1=1'
        assert status_s2 == 1, f'Seat 2 should have status=1 (RESERVED), got {status_s2}'

        # Check seat A-1-2-1 (index 5: row 2, seat 1 in 5-seat rows)
        bit0_s3 = kvrocks_client_sync_for_test.getbit(bf_key, 10)
        bit1_s3 = kvrocks_client_sync_for_test.getbit(bf_key, 11)
        status_s3 = bit0_s3 * 2 + bit1_s3
        assert (bit0_s3, bit1_s3) == (0, 1), 'Seat in row 2 should have bit0=0, bit1=1'
        assert status_s3 == 1, f'Seat in row 2 should have status=1 (RESERVED), got {status_s3}'

        # Verify stats show reserved, not sold
        stats_key = _make_key(f'section_stats:{event_id}:A-1')
        stats = kvrocks_client_sync_for_test.hgetall(stats_key)
        assert int(stats['available']) == 7  # 10 - 3
        assert int(stats['reserved']) == 3
        assert int(stats.get('sold', 0)) == 0  # Should be 0, not 3!
