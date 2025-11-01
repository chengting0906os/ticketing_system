"""
Unit tests for SeatFinder

Tests consecutive seat finding logic using bitfield operations.
"""

import os

import pytest

from src.platform.state.kvrocks_client import kvrocks_client
from src.service.seat_reservation.driven_adapter.seat_reservation_helper.seat_finder import (
    SeatFinder,
)


# Get key prefix for test isolation
_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', 'test_')


def _make_key(key: str) -> str:
    """Add prefix to key for test isolation"""
    return f'{_KEY_PREFIX}{key}'


class TestSeatFinder:
    """Unit tests for SeatFinder consecutive seat search"""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_calculate_seat_index(self):
        finder = SeatFinder()

        # Row 1, Seat 1, 5 seats per row → index 0
        assert finder._calculate_seat_index(1, 1, 5) == 0

        # Row 1, Seat 2, 5 seats per row → index 1
        assert finder._calculate_seat_index(1, 2, 5) == 1

        # Row 2, Seat 1, 5 seats per row → index 5
        assert finder._calculate_seat_index(2, 1, 5) == 5

        # Row 2, Seat 3, 5 seats per row → index 7
        assert finder._calculate_seat_index(2, 3, 5) == 7

        # Row 3, Seat 2, 10 seats per row → index 21
        assert finder._calculate_seat_index(3, 2, 10) == 21

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_single_row_success(self, kvrocks_client_sync_for_test):
        # Given: Setup bitfield with all seats available (00)
        finder = SeatFinder()
        bf_key = _make_key('test_seats_bf:1:A-1')
        client = kvrocks_client.get_client()

        # Clear any existing data
        await client.delete(bf_key)

        # 1 row, 5 seats, all available (bitfield defaults to 0)
        rows = 1
        seats_per_row = 5

        # When: Find 3 consecutive seats
        result = await finder.find_consecutive_seats(
            bf_key=bf_key, rows=rows, seats_per_row=seats_per_row, quantity=3
        )

        # Then: Should find seats 1-3 in row 1
        assert result is not None
        assert len(result) == 3
        assert result == [(1, 1, 0), (1, 2, 1), (1, 3, 2)]

        # Cleanup
        await client.delete(bf_key)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_with_reserved_seats(self, kvrocks_client_sync_for_test):
        # Given: Setup bitfield with some seats reserved
        finder = SeatFinder()
        bf_key = _make_key('test_seats_bf:2:A-1')
        client = kvrocks_client.get_client()

        await client.delete(bf_key)

        # 1 row, 5 seats
        # Mark seats 1-2 as RESERVED (01)
        await client.setbit(bf_key, 0, 0)  # seat 1, bit0
        await client.setbit(bf_key, 1, 1)  # seat 1, bit1 → RESERVED
        await client.setbit(bf_key, 2, 0)  # seat 2, bit0
        await client.setbit(bf_key, 3, 1)  # seat 2, bit1 → RESERVED
        # Seats 3-5 remain AVAILABLE (00)

        # When: Find 2 consecutive seats
        result = await finder.find_consecutive_seats(
            bf_key=bf_key, rows=1, seats_per_row=5, quantity=2
        )

        # Then: Should find seats 3-4
        assert result is not None
        assert len(result) == 2
        assert result == [(1, 3, 2), (1, 4, 3)]

        # Cleanup
        await client.delete(bf_key)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_multiple_rows(self, kvrocks_client_sync_for_test):
        """Test finding consecutive seats across multiple rows"""
        # Given: Setup 2 rows, first row mostly reserved
        finder = SeatFinder()
        bf_key = _make_key('test_seats_bf:3:A-1')
        client = kvrocks_client.get_client()

        await client.delete(bf_key)

        # Row 1: Reserve all except last seat
        # 3 seats per row
        for seat_idx in range(2):  # Reserve seats 1-2
            offset = seat_idx * 2
            await client.setbit(bf_key, offset, 0)
            await client.setbit(bf_key, offset + 1, 1)

        # Row 2: All available

        # When: Find 2 consecutive seats
        result = await finder.find_consecutive_seats(
            bf_key=bf_key, rows=2, seats_per_row=3, quantity=2
        )

        # Then: Should find seats in row 2
        assert result is not None
        assert len(result) == 2
        # Row 2, Seats 1-2 (indices 3-4)
        assert result == [(2, 1, 3), (2, 2, 4)]

        # Cleanup
        await client.delete(bf_key)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_not_found(self, kvrocks_client_sync_for_test):
        """Test when no consecutive seats are available"""
        # Given: Setup seats with gaps (no consecutive pairs)
        finder = SeatFinder()
        bf_key = _make_key('test_seats_bf:4:A-1')
        client = kvrocks_client.get_client()

        await client.delete(bf_key)

        # 1 row, 5 seats: Reserve seats 2 and 4 (creating gaps)
        # Pattern: A R A R A (no 2 consecutive)
        await client.setbit(bf_key, 2, 0)  # seat 2, bit0
        await client.setbit(bf_key, 3, 1)  # seat 2, bit1 → RESERVED
        await client.setbit(bf_key, 6, 0)  # seat 4, bit0
        await client.setbit(bf_key, 7, 1)  # seat 4, bit1 → RESERVED

        # When: Try to find 2 consecutive seats
        result = await finder.find_consecutive_seats(
            bf_key=bf_key, rows=1, seats_per_row=5, quantity=2
        )

        # Then: Should return None
        assert result is None

        # Cleanup
        await client.delete(bf_key)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_exact_match(self, kvrocks_client_sync_for_test):
        # Given: Setup with exactly N consecutive available seats
        finder = SeatFinder()
        bf_key = _make_key('test_seats_bf:5:A-1')
        client = kvrocks_client.get_client()

        await client.delete(bf_key)

        # 1 row, 3 seats, all available

        # When: Find exactly 3 consecutive seats
        result = await finder.find_consecutive_seats(
            bf_key=bf_key, rows=1, seats_per_row=3, quantity=3
        )

        # Then: Should find all seats
        assert result is not None
        assert len(result) == 3
        assert result == [(1, 1, 0), (1, 2, 1), (1, 3, 2)]

        # Cleanup
        await client.delete(bf_key)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_skip_sold_seats(self, kvrocks_client_sync_for_test):
        # Given: Setup with SOLD seats
        finder = SeatFinder()
        bf_key = _make_key('test_seats_bf:6:A-1')
        client = kvrocks_client.get_client()

        await client.delete(bf_key)

        # 1 row, 5 seats
        # Mark seat 2 as SOLD (10)
        await client.setbit(bf_key, 2, 1)  # seat 2, bit0 → SOLD
        await client.setbit(bf_key, 3, 0)  # seat 2, bit1

        # When: Find 3 consecutive seats
        result = await finder.find_consecutive_seats(
            bf_key=bf_key, rows=1, seats_per_row=5, quantity=3
        )

        # Then: Should find seats 3-5 (skipping sold seat 2)
        assert result is not None
        assert len(result) == 3
        assert result == [(1, 3, 2), (1, 4, 3), (1, 5, 4)]

        # Cleanup
        await client.delete(bf_key)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_finds_earliest_available(
        self, kvrocks_client_sync_for_test
    ):
        # Given: Multiple consecutive groups available
        finder = SeatFinder()
        bf_key = _make_key('test_seats_bf:7:A-1')
        client = kvrocks_client.get_client()

        await client.delete(bf_key)

        # 2 rows, 4 seats per row
        # Row 1: R R A A (seats 3-4 available)
        # Row 2: A A A A (all available)
        await client.setbit(bf_key, 0, 0)  # seat 1, RESERVED
        await client.setbit(bf_key, 1, 1)
        await client.setbit(bf_key, 2, 0)  # seat 2, RESERVED
        await client.setbit(bf_key, 3, 1)

        # When: Find 2 consecutive seats
        result = await finder.find_consecutive_seats(
            bf_key=bf_key, rows=2, seats_per_row=4, quantity=2
        )

        # Then: Should find row 1, seats 3-4 (earliest)
        assert result is not None
        assert len(result) == 2
        assert result == [(1, 3, 2), (1, 4, 3)]

        # Cleanup
        await client.delete(bf_key)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_quantity_one(self, kvrocks_client_sync_for_test):
        # Given: Setup with some reserved seats
        finder = SeatFinder()
        bf_key = _make_key('test_seats_bf:8:A-1')
        client = kvrocks_client.get_client()

        await client.delete(bf_key)

        # 1 row, 3 seats
        # Reserve seat 1
        await client.setbit(bf_key, 0, 0)
        await client.setbit(bf_key, 1, 1)

        # When: Find 1 seat
        result = await finder.find_consecutive_seats(
            bf_key=bf_key, rows=1, seats_per_row=3, quantity=1
        )

        # Then: Should find seat 2
        assert result is not None
        assert len(result) == 1
        assert result == [(1, 2, 1)]

        # Cleanup
        await client.delete(bf_key)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_empty_venue(self, kvrocks_client_sync_for_test):
        # Given: Empty bitfield (all seats available)
        finder = SeatFinder()
        bf_key = _make_key('test_seats_bf:9:A-1')
        client = kvrocks_client.get_client()

        await client.delete(bf_key)

        # When: Find consecutive seats
        result = await finder.find_consecutive_seats(
            bf_key=bf_key, rows=3, seats_per_row=10, quantity=5
        )

        # Then: Should find first 5 seats in row 1
        assert result is not None
        assert len(result) == 5
        expected = [(1, i + 1, i) for i in range(5)]
        assert result == expected

        # Cleanup
        await client.delete(bf_key)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_full_venue(self, kvrocks_client_sync_for_test):
        # Given: All seats reserved
        finder = SeatFinder()
        bf_key = _make_key('test_seats_bf:10:A-1')
        client = kvrocks_client.get_client()

        await client.delete(bf_key)

        rows = 2
        seats_per_row = 3
        total_seats = rows * seats_per_row

        # Mark all seats as RESERVED
        for seat_idx in range(total_seats):
            offset = seat_idx * 2
            await client.setbit(bf_key, offset, 0)
            await client.setbit(bf_key, offset + 1, 1)

        # When: Try to find consecutive seats
        result = await finder.find_consecutive_seats(
            bf_key=bf_key, rows=rows, seats_per_row=seats_per_row, quantity=2
        )

        # Then: Should return None
        assert result is None

        # Cleanup
        await client.delete(bf_key)
