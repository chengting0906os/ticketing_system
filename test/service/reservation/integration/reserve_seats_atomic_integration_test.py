"""
Integration test for reserve_seats_atomic using Pipeline

Tests the unified seat reservation implementation supporting two modes:
1. manual mode - Reserve specific seat IDs
2. best_available mode - Automatically find and reserve consecutive seats
"""

import os
from typing import cast

import orjson
import pytest
from src.service.reservation.driven_adapter.seat_state_command_handler_impl import (
    SeatStateCommandHandlerImpl,
)
import uuid_utils as uuid

from src.platform.config.di import container
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.ticketing.driven_adapter.state.init_event_and_tickets_state_handler_impl import (
    InitEventAndTicketsStateHandlerImpl,
)
from test.kvrocks_test_client import kvrocks_test_client


# Get key prefix for test isolation
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', 'test_')


def _make_key(key: str) -> str:
    """Add prefix to key for test isolation"""
    return f'{_KEY_PREFIX}{key}'


def _get_section_stats_from_json(client, event_id: int, section_id: str) -> dict:
    """
    Helper function to fetch section stats from event_state JSON
    """
    event_state_key = _make_key(f'event_state:{event_id}')
    result = client.execute_command('JSON.GET', event_state_key, '$')
    event_state = orjson.loads(cast(bytes, result))[0]
    section_name = section_id.split('-')[0]
    subsection_num = section_id.split('-')[1]
    subsection_data = (
        event_state.get('sections', {})
        .get(section_name, {})
        .get('subsections', {})
        .get(subsection_num, {})
    )
    stats = subsection_data.get('stats', {})

    # Return dict with string keys (compatible with test assertions)
    return {
        'available': str(stats.get('available', 0)),
        'reserved': str(stats.get('reserved', 0)),
        'sold': str(stats.get('sold', 0)),
        'total': str(stats.get('total', 0)),
        'updated_at': str(stats.get('updated_at', 0)),
    }


@pytest.fixture
async def seat_handler() -> SeatStateCommandHandlerImpl:
    """Create seat state command handler with proper DI"""
    await kvrocks_client.initialize()
    return container.seat_state_command_handler()


@pytest.fixture
async def init_handler() -> InitEventAndTicketsStateHandlerImpl:
    """Create seat initialization handler"""
    await kvrocks_client.initialize()
    return InitEventAndTicketsStateHandlerImpl()


@pytest.fixture(scope='function')
def unique_event_id():
    """Generate unique event_id for each test to avoid conflicts in parallel execution"""
    import random
    import time

    # Use timestamp (microseconds) + random for strong uniqueness guarantee
    event_id = int(time.time() * 1000000) % 10000000 + random.randint(1, 9999)

    return event_id


class TestReserveSeatsAtomicManualMode:
    """Test reserve_seats_atomic() - Manual Mode (manual seat selection)"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reserve_single_seat_success(self, seat_handler, init_handler, unique_event_id):
        # Get sync client for verification
        client = kvrocks_test_client.connect()

        # Given: Initialize seats (compact format)
        config = {
            'rows': 1,
            'cols': 3,
            'sections': [{'name': 'A', 'price': 1000, 'subsections': 1}],
        }
        event_id = unique_event_id
        result = await init_handler.initialize_seats_from_config(
            event_id=event_id, seating_config=config
        )

        # When: Reserve one seat using manual mode
        booking_id = str(uuid.uuid7())
        result = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=booking_id,
            buyer_id=1,
            mode='manual',
            section='A',
            subsection=1,
            quantity=1,
            seat_ids=['1-1'],
        )

        # Then: Should succeed
        assert result['success'] is True
        assert result['reserved_seats'] == ['A-1-1-1']

        # Verify seat status is RESERVED (u2 encoding)
        # Status encoding: 0=AVAILABLE, 1=RESERVED, 2=SOLD
        bf_key = _make_key(f'seats_bf:{event_id}:A-1')
        status = client.execute_command('BITFIELD', bf_key, 'GET', 'u2', 0)
        assert status == [1]  # RESERVED

        # Verify stats updated
        stats = _get_section_stats_from_json(client, event_id, 'A-1')
        assert int(stats['available']) == 2  # 3 - 1
        assert int(stats['reserved']) == 1

    @pytest.mark.smoke
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reserve_multiple_seats_atomically(
        self, seat_handler, init_handler, unique_event_id
    ):
        # Get sync client for verification
        client = kvrocks_test_client.connect()

        # Given: Initialize seats (compact format)
        config = {
            'rows': 2,
            'cols': 3,
            'sections': [{'name': 'A', 'price': 1000, 'subsections': 1}],
        }
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # When: Reserve 3 seats using manual mode
        booking_id = str(uuid.uuid7())
        result = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=booking_id,
            buyer_id=2,
            mode='manual',
            section='A',
            subsection=1,
            quantity=3,
            seat_ids=['1-1', '1-2', '2-1'],
        )

        # Then: Should succeed
        assert result['success'] is True
        assert len(result['reserved_seats']) == 3
        # All reserved seats should be in full format
        expected_seats = ['A-1-1-1', 'A-1-1-2', 'A-1-2-1']
        assert sorted(result['reserved_seats']) == sorted(expected_seats)

        # Verify stats
        stats = _get_section_stats_from_json(client, event_id, 'A-1')
        assert int(stats['available']) == 3  # 6 - 3
        assert int(stats['reserved']) == 3

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reserve_already_reserved_seat_fails(
        self, seat_handler, init_handler, unique_event_id
    ):
        # Get sync client for verification
        client = kvrocks_test_client.connect()

        # Given: Initialize and reserve a seat (compact format)
        config = {
            'rows': 1,
            'cols': 2,
            'sections': [{'name': 'A', 'price': 1000, 'subsections': 1}],
        }
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # Reserve seat A-1-1-1
        booking_id_1 = str(uuid.uuid7())
        await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=booking_id_1,
            buyer_id=3,
            mode='manual',
            section='A',
            subsection=1,
            quantity=1,
            seat_ids=['1-1'],
        )

        # When: Try to reserve the same seat again
        booking_id_2 = str(uuid.uuid7())
        result = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=booking_id_2,
            buyer_id=4,
            mode='manual',
            section='A',
            subsection=1,
            quantity=1,
            seat_ids=['1-1'],
        )

        # Then: Should fail
        assert result['success'] is False

        # Stats should not change
        stats = _get_section_stats_from_json(client, event_id, 'A-1')
        assert int(stats['available']) == 1  # Still 1
        assert int(stats['reserved']) == 1  # Still 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_partial_reservation_failure(self, seat_handler, init_handler, unique_event_id):
        # Given: Initialize seats and reserve one (compact format)
        config = {
            'rows': 1,
            'cols': 3,
            'sections': [{'name': 'A', 'price': 1000, 'subsections': 1}],
        }
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # Reserve seat A-1-1-2
        booking_id_1 = str(uuid.uuid7())
        await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=booking_id_1,
            buyer_id=5,
            mode='manual',
            section='A',
            subsection=1,
            quantity=1,
            seat_ids=['1-2'],
        )

        # When: Try to reserve 3 seats including the reserved one
        booking_id_2 = str(uuid.uuid7())
        result = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=booking_id_2,
            buyer_id=6,
            mode='manual',
            section='A',
            subsection=1,
            quantity=3,
            seat_ids=['1-1', '1-2', '1-3'],
        )

        # Then: Should fail (manual mode requires ALL seats to be available)
        assert result['success'] is False

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reserve_seats_updates_timestamp(
        self, seat_handler, init_handler, unique_event_id
    ):
        # Get sync client for verification
        client = kvrocks_test_client.connect()

        # Given: Initialize seats (compact format)
        config = {
            'rows': 1,
            'cols': 1,
            'sections': [{'name': 'A', 'price': 1000, 'subsections': 1}],
        }
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # Get initial timestamp
        initial_stats = _get_section_stats_from_json(client, event_id, 'A-1')
        initial_timestamp = initial_stats['updated_at']

        # When: Reserve a seat
        booking_id = str(uuid.uuid7())
        await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=booking_id,
            buyer_id=7,
            mode='manual',
            section='A',
            subsection=1,
            quantity=1,
            seat_ids=['1-1'],
        )

        # Then: Timestamp should be updated
        updated_stats = _get_section_stats_from_json(client, event_id, 'A-1')
        updated_timestamp = updated_stats['updated_at']
        assert updated_timestamp >= initial_timestamp

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reserve_seats_across_multiple_sections(
        self, seat_handler, init_handler, unique_event_id
    ):
        """Test reserving seats from different sections atomically"""
        # Get sync client for verification
        client = kvrocks_test_client.connect()

        # Given: Initialize multiple sections (compact format)
        config = {
            'rows': 1,
            'cols': 2,
            'sections': [
                {'name': 'A', 'price': 3000, 'subsections': 1},
                {'name': 'B', 'price': 2000, 'subsections': 1},
            ],
        }
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # When: Reserve seats from both sections (need separate calls for different sections)
        booking_id_a = str(uuid.uuid7())
        booking_id_b = str(uuid.uuid7())

        result_a = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=booking_id_a,
            buyer_id=8,
            mode='manual',
            section='A',
            subsection=1,
            quantity=1,
            seat_ids=['1-1'],
        )

        result_b = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=booking_id_b,  # Different booking_id to avoid idempotency check
            buyer_id=8,
            mode='manual',
            section='B',
            subsection=1,
            quantity=1,
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
        stats_a = _get_section_stats_from_json(client, event_id, 'A-1')
        stats_b = _get_section_stats_from_json(client, event_id, 'B-1')
        assert int(stats_a['reserved']) == 1
        assert int(stats_b['reserved']) == 1


class TestReserveSeatsAtomicBestAvailableMode:
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_and_reserve_consecutive_seats_in_single_row(
        self, seat_handler, init_handler, unique_event_id
    ):
        # Get sync client for verification
        client = kvrocks_test_client.connect()

        # Given: Initialize seats with 1 row, 5 seats (compact format)
        config = {
            'rows': 1,
            'cols': 5,
            'sections': [{'name': 'A', 'price': 1000, 'subsections': 1}],
        }
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # When: Request 3 consecutive seats (best_available mode)
        booking_id = str(uuid.uuid7())
        result = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=booking_id,
            buyer_id=1,
            mode='best_available',
            section='A',
            subsection=1,
            quantity=3,
            # Config from upstream (avoids redundant Kvrocks lookups)
            rows=1,
            cols=5,
            price=1000,
        )

        # Then: Should successfully reserve 3 consecutive seats
        assert result['success'] is True
        assert len(result['reserved_seats']) == 3

        # Verify they are consecutive in same row
        seat_ids = result['reserved_seats']
        assert seat_ids == ['A-1-1-1', 'A-1-1-2', 'A-1-1-3']

        # Verify stats updated
        stats = _get_section_stats_from_json(client, event_id, 'A-1')
        assert int(stats['available']) == 2  # 5 - 3
        assert int(stats['reserved']) == 3

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_across_multiple_rows(
        self, seat_handler, init_handler, unique_event_id
    ):
        # Given: Initialize seats with 2 rows, 3 seats per row (compact format)
        # Reserve 2 seats in first row, leaving only 1 available
        config = {
            'rows': 2,
            'cols': 3,
            'sections': [{'name': 'A', 'price': 1000, 'subsections': 1}],
        }
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # Reserve 2 seats in first row
        booking_id_1 = str(uuid.uuid7())
        await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=booking_id_1,
            buyer_id=99,
            mode='manual',
            section='A',
            subsection=1,
            quantity=2,
            seat_ids=['1-1', '1-2'],
        )

        # When: Request 2 consecutive seats
        booking_id_2 = str(uuid.uuid7())
        result = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=booking_id_2,
            buyer_id=1,
            mode='best_available',
            section='A',
            subsection=1,
            quantity=2,
            # Config from upstream (avoids redundant Kvrocks lookups)
            rows=2,
            cols=3,
            price=1000,
        )

        # Then: Should find consecutive seats in second row
        assert result['success'] is True
        seat_ids = result['reserved_seats']
        assert seat_ids == ['A-1-2-1', 'A-1-2-2']  # Row 2, seats 1-2

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_no_consecutive_seats_available(
        self, seat_handler, init_handler, unique_event_id
    ):
        # Given: Initialize 1 row with 3 seats, reserve middle seat (compact format)
        config = {
            'rows': 1,
            'cols': 3,
            'sections': [{'name': 'A', 'price': 1000, 'subsections': 1}],
        }
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # Reserve middle seat to break continuity
        booking_id_1 = str(uuid.uuid7())
        await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=booking_id_1,
            buyer_id=99,
            mode='manual',
            section='A',
            subsection=1,
            quantity=1,
            seat_ids=['1-2'],
        )

        # When: Request 2 consecutive seats (but only [1] and [3] available as scattered singles)
        booking_id_2 = str(uuid.uuid7())
        result = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=booking_id_2,
            buyer_id=1,
            mode='best_available',
            section='A',
            subsection=1,
            quantity=2,
            # Config from upstream (avoids redundant Kvrocks lookups)
            rows=1,
            cols=3,
            price=1000,
        )

        # Then: Should succeed by returning 2 scattered single seats
        assert result['success'] is True
        assert len(result['reserved_seats']) == 2
        assert set(result['reserved_seats']) == {'A-1-1-1', 'A-1-1-3'}  # Seats 1 and 3

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_best_position_for_consecutive_seats(
        self, seat_handler, init_handler, unique_event_id
    ):
        # Given: Multiple rows with available seats (compact format)
        config = {
            'rows': 3,
            'cols': 4,
            'sections': [{'name': 'A', 'price': 1000, 'subsections': 1}],
        }
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # Reserve some seats to create gaps
        booking_id_1 = str(uuid.uuid7())
        await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=booking_id_1,
            buyer_id=98,
            mode='manual',
            section='A',
            subsection=1,
            quantity=2,
            seat_ids=['1-1', '1-2'],  # Row 1: XX--
        )

        # When: Request 2 consecutive seats
        booking_id_2 = str(uuid.uuid7())
        result = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=booking_id_2,
            buyer_id=1,
            mode='best_available',
            section='A',
            subsection=1,
            quantity=2,
            # Config from upstream (avoids redundant Kvrocks lookups)
            rows=3,
            cols=4,
            price=1000,
        )

        # Then: Should choose row 1 seats 3-4 (earliest available consecutive pair)
        assert result['success'] is True
        assert result['reserved_seats'] == ['A-1-1-3', 'A-1-1-4']

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reserved_status_not_sold(self, seat_handler, init_handler, unique_event_id):
        """
        Test that reserved seats have correct status (RESERVED not SOLD)

        This test specifically validates the bug fix where reserved seats
        were incorrectly showing as 'sold' instead of 'reserved'.

        Bug: Bitfield encoding was setting bit0=1, bit1=0 which resulted in
             status = 1*2 + 0 = 2 (SOLD) instead of 1 (RESERVED)
        Fix: Changed to bit0=0, bit1=1 which gives status = 0*2 + 1 = 1 (RESERVED)
        """
        # Get sync client for verification
        client = kvrocks_test_client.connect()

        # Given: Initialize seats (compact format)
        config = {
            'rows': 2,
            'cols': 5,
            'sections': [{'name': 'A', 'price': 3000, 'subsections': 1}],
        }
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # When: Reserve 3 seats using manual mode
        booking_id = str(uuid.uuid7())
        result = await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=booking_id,
            buyer_id=1,
            mode='manual',
            section='A',
            subsection=1,
            quantity=3,
            seat_ids=['1-1', '1-2', '2-1'],
        )

        # Then: Reservation should succeed
        assert result['success'] is True
        assert len(result['reserved_seats']) == 3

        # Verify each reserved seat has correct bitfield encoding
        bf_key = _make_key(f'seats_bf:{event_id}:A-1')

        # Check seat A-1-1-1 (index 0) - RESERVED status = 1
        status_s1 = client.execute_command('BITFIELD', bf_key, 'GET', 'u2', 0)
        assert status_s1 == [1], 'Seat 1 should have status=1 (RESERVED)'

        # Check seat A-1-1-2 (index 1) - RESERVED status = 1
        status_s2 = client.execute_command('BITFIELD', bf_key, 'GET', 'u2', 2)
        assert status_s2 == [1], 'Seat 2 should have status=1 (RESERVED)'

        # Check seat A-1-2-1 (index 5: row 2, seat 1 in 5-seat rows) - RESERVED status = 1
        status_s3 = client.execute_command('BITFIELD', bf_key, 'GET', 'u2', 10)
        assert status_s3 == [1], 'Seat in row 2 should have status=1 (RESERVED)'

        # Verify stats show reserved, not sold
        stats = _get_section_stats_from_json(client, event_id, 'A-1')
        assert int(stats['available']) == 7  # 10 - 3
        assert int(stats['reserved']) == 3
        assert int(stats.get('sold', '0')) == 0  # Should be 0, not 3!
