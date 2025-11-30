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
    return f'{_KEY_PREFIX}{key}'


async def _set_seat_state(client, bf_key: str, seat_index: int, state: int):
    offset = seat_index * 2
    await client.execute_command('BITFIELD', bf_key, 'SET', 'u2', offset, state)


# =============================================================================
# Integration Tests (require Kvrocks)
# =============================================================================
class TestSeatFinder:
    @pytest.fixture(autouse=True)
    async def setup_kvrocks(self):
        await kvrocks_client.initialize()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_single_row_success(self):
        # Given: Setup bitfield with all seats available (00)
        finder: SeatFinder = SeatFinder()
        bf_key = _make_key('test_seats_bf:1:A-1')

        # 1 row, 5 seats, all available (bitfield defaults to 0)
        rows = 1
        cols = 5

        # When: Find 3 consecutive seats
        result = await finder.find_consecutive_seats(
            bf_key=bf_key, rows=rows, cols=cols, quantity=3
        )

        # Then: Should find seats 1-3 in row 1
        assert result is not None
        assert len(result) == 3
        assert result == [(1, 1, 0), (1, 2, 1), (1, 3, 2)]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_with_reserved_seats(self):
        # Given: Setup bitfield with some seats reserved
        finder: SeatFinder = SeatFinder()
        bf_key = _make_key('test_seats_bf:2:A-1')
        client = kvrocks_client.get_client()

        # 1 row, 5 seats
        # Mark seats 1-2 as RESERVED (01)
        await _set_seat_state(client, bf_key, 0, 1)  # seat 1 → RESERVED
        await _set_seat_state(client, bf_key, 1, 1)  # seat 2 → RESERVED
        # Seats 3-5 remain AVAILABLE (00)

        # When: Find 2 consecutive seats
        result = await finder.find_consecutive_seats(bf_key=bf_key, rows=1, cols=5, quantity=2)

        # Then: Should find seats 3-4
        assert result is not None
        assert len(result) == 2
        assert result == [(1, 3, 2), (1, 4, 3)]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_multiple_rows(self):
        """Test finding consecutive seats across multiple rows"""
        # Given: Setup 2 rows, first row mostly reserved
        finder: SeatFinder = SeatFinder()
        bf_key = _make_key('test_seats_bf:3:A-1')
        client = kvrocks_client.get_client()

        # Row 1: Reserve all except last seat
        # 3 seats per row
        for seat_idx in range(2):  # Reserve seats 1-2
            await _set_seat_state(client, bf_key, seat_idx, 1)  # RESERVED

        # Row 2: All available

        # When: Find 2 consecutive seats
        result = await finder.find_consecutive_seats(bf_key=bf_key, rows=2, cols=3, quantity=2)

        # Then: Should find seats in row 2
        assert result is not None
        assert len(result) == 2
        # Row 2, Seats 1-2 (indices 3-4)
        assert result == [(2, 1, 3), (2, 2, 4)]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_but_scatterd_seats_exsit(self):
        """Test when no consecutive seats available but scattered seats exist"""
        # Given: Setup seats with gaps (no consecutive pairs)
        finder: SeatFinder = SeatFinder()
        bf_key = _make_key('test_seats_bf:4:A-1')
        client = kvrocks_client.get_client()

        # 1 row, 5 seats: Reserve seats 2 and 4 (creating gaps)
        # Pattern: A R A R A (no 2 consecutive, but 3 singles available)
        await _set_seat_state(client, bf_key, 1, 1)  # seat 2 → RESERVED
        await _set_seat_state(client, bf_key, 3, 1)  # seat 4 → RESERVED

        # When: Try to find 2 consecutive seats
        result = await finder.find_consecutive_seats(bf_key=bf_key, rows=1, cols=5, quantity=2)

        # Then: Should return 2 scattered singles (seats 1 and 3)
        assert result is not None
        assert len(result) == 2
        assert result == [(1, 1, 0), (1, 3, 2)]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_exact_match(self):
        # Given: Setup with exactly N consecutive available seats
        finder: SeatFinder = SeatFinder()
        bf_key = _make_key('test_seats_bf:5:A-1')

        # 1 row, 3 seats, all available

        # When: Find exactly 3 consecutive seats
        result = await finder.find_consecutive_seats(bf_key=bf_key, rows=1, cols=3, quantity=3)

        # Then: Should find all seats
        assert result is not None
        assert len(result) == 3
        assert result == [(1, 1, 0), (1, 2, 1), (1, 3, 2)]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_skip_sold_seats(self):
        # Given: Setup with SOLD seats
        finder: SeatFinder = SeatFinder()
        bf_key = _make_key('test_seats_bf:6:A-1')
        client = kvrocks_client.get_client()

        # 1 row, 5 seats
        # Mark seat 2 as SOLD (10)
        await _set_seat_state(client, bf_key, 1, 2)  # seat 2 → SOLD

        # When: Find 3 consecutive seats
        result = await finder.find_consecutive_seats(bf_key=bf_key, rows=1, cols=5, quantity=3)

        # Then: Should find seats 3-5 (skipping sold seat 2)
        assert result is not None
        assert len(result) == 3
        assert result == [(1, 3, 2), (1, 4, 3), (1, 5, 4)]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_finds_earliest_available(self):
        # Given: Multiple consecutive groups available
        finder: SeatFinder = SeatFinder()
        bf_key = _make_key('test_seats_bf:7:A-1')
        client = kvrocks_client.get_client()

        # 2 rows, 4 seats per row
        # Row 1: R R A A (seats 3-4 available)
        # Row 2: A A A A (all available)
        await _set_seat_state(client, bf_key, 0, 1)  # seat 1 → RESERVED
        await _set_seat_state(client, bf_key, 1, 1)  # seat 2 → RESERVED

        # When: Find 2 consecutive seats
        result = await finder.find_consecutive_seats(bf_key=bf_key, rows=2, cols=4, quantity=2)

        # Then: Should find row 1, seats 3-4 (earliest)
        assert result is not None
        assert len(result) == 2
        assert result == [(1, 3, 2), (1, 4, 3)]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_quantity_one(self):
        # Given: Setup with some reserved seats
        finder: SeatFinder = SeatFinder()
        bf_key = _make_key('test_seats_bf:8:A-1')
        client = kvrocks_client.get_client()

        # 1 row, 3 seats
        # Reserve seat 1
        await _set_seat_state(client, bf_key, 0, 1)  # seat 1 → RESERVED

        # When: Find 1 seat
        result = await finder.find_consecutive_seats(bf_key=bf_key, rows=1, cols=3, quantity=1)

        # Then: Should find seat 2
        assert result is not None
        assert len(result) == 1
        assert result == [(1, 2, 1)]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_empty_venue(self):
        # Given: Empty bitfield (all seats available)
        finder: SeatFinder = SeatFinder()
        bf_key = _make_key('test_seats_bf:9:A-1')

        # When: Find 4 consecutive seats (max allowed)
        result = await finder.find_consecutive_seats(bf_key=bf_key, rows=3, cols=10, quantity=4)

        # Then: Should find first 4 seats in row 1
        assert result is not None
        assert len(result) == 4
        expected = [(1, i + 1, i) for i in range(4)]
        assert result == expected

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_full_venue(self):
        # Given: All seats reserved
        finder: SeatFinder = SeatFinder()
        bf_key = _make_key('test_seats_bf:10:A-1')
        client = kvrocks_client.get_client()

        rows = 2
        cols = 3
        total_seats = rows * cols

        # Mark all seats as RESERVED
        for seat_idx in range(total_seats):
            await _set_seat_state(client, bf_key, seat_idx, 1)  # RESERVED

        # When: Try to find consecutive seats
        result = await finder.find_consecutive_seats(
            bf_key=bf_key, rows=rows, cols=cols, quantity=2
        )

        # Then: Should return None
        assert result is None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_smart_fallback(self):
        """
        Test smart fallback: Return largest consecutive blocks when perfect consecutive not found.

        Scenario:
        - Need 4 seats (max allowed)
        - Row 1: R A A R R (2 consecutive: seats 2-3)
        - Row 2: A A R R R (2 consecutive: seats 1-2)
        - Row 3: R R R R R (0 consecutive)

        Expected: Return row 1 (2 seats) + row 2 (2 seats) = 4 seats
        """
        finder: SeatFinder = SeatFinder()
        bf_key = _make_key('test_seats_bf:11:A-1')
        client = kvrocks_client.get_client()

        rows = 3
        cols = 5

        # Row 1: Reserve seats 1, 4, 5 → leaves seats 2-3 available
        await _set_seat_state(client, bf_key, 0, 1)  # seat 1 → RESERVED
        await _set_seat_state(client, bf_key, 3, 1)  # seat 4 → RESERVED
        await _set_seat_state(client, bf_key, 4, 1)  # seat 5 → RESERVED

        # Row 2: Reserve seats 3-5 → leaves seats 1-2 available
        for seat_num in [3, 4, 5]:
            seat_idx = (2 - 1) * cols + (seat_num - 1)  # row 2
            await _set_seat_state(client, bf_key, seat_idx, 1)  # RESERVED

        # Row 3: Reserve all seats
        for seat_num in range(1, 6):
            seat_idx = (3 - 1) * cols + (seat_num - 1)  # row 3
            await _set_seat_state(client, bf_key, seat_idx, 1)  # RESERVED

        # When: Find 4 consecutive seats (won't find perfect consecutive)
        result = await finder.find_consecutive_seats(
            bf_key=bf_key, rows=rows, cols=cols, quantity=4
        )

        # Then: Should return largest blocks first (both are size 2)
        assert result is not None
        assert len(result) == 4

        # Expected: Row 1 (seats 2-3) + Row 2 (seats 1-2)
        # Row 1, seats 2-4
        row1_seats = [(1, 2, 1), (1, 3, 2)]
        # Row 2, seats 1-2
        row2_seats = [(2, 1, 5), (2, 2, 6)]

        expected = row1_seats + row2_seats
        assert result == expected

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_bitfield_optimization_works_correctly(self):
        """
        Test that BITFIELD batch read works correctly (performance optimization)

        Verifies that BITFIELD GET u2 returns same results as individual GETBIT calls
        """
        finder: SeatFinder = SeatFinder()
        bf_key = _make_key('test_seats_bf:12:A-1')
        client = kvrocks_client.get_client()

        # Setup: 2 rows, 10 seats per row
        # Row 1: AVAILABLE RESERVED SOLD AVAILABLE RESERVED SOLD AVAILABLE AVAILABLE SOLD RESERVED
        # Row 2: All AVAILABLE
        rows = 2
        cols = 10

        # Set various seat states in Row 1 using BITFIELD
        # Note: Must use BITFIELD SET instead of SETBIT for compatibility with BITFIELD GET in Kvrocks
        seat_states = [
            0,  # Seat 1: AVAILABLE (00)
            1,  # Seat 2: RESERVED (01)
            2,  # Seat 3: SOLD (10)
            0,  # Seat 4: AVAILABLE (00)
            1,  # Seat 5: RESERVED (01)
            2,  # Seat 6: SOLD (10)
            0,  # Seat 7: AVAILABLE (00)
            0,  # Seat 8: AVAILABLE (00)
            2,  # Seat 9: SOLD (10)
            1,  # Seat 10: RESERVED (01)
        ]

        for seat_num, status in enumerate(seat_states, start=1):
            seat_idx = (1 - 1) * cols + (seat_num - 1)  # Row 1
            offset = seat_idx * 2
            await client.execute_command('BITFIELD', bf_key, 'SET', 'u2', offset, status)

        # When: Find 2 consecutive seats (should find seats 7-8 in Row 1)
        result = await finder.find_consecutive_seats(
            bf_key=bf_key, rows=rows, cols=cols, quantity=2
        )

        # Then: Should find seats 7-8 (the only 2 consecutive available seats in Row 1)
        assert result is not None
        assert len(result) == 2
        assert result == [(1, 7, 6), (1, 8, 7)]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_scattered_singles_accepted(self):
        """
        Test Lua script acceptance of scattered single seats when consecutive not found.

        Behavior: Lua script returns any available seats (including scattered singles)
        This ensures users can still purchase tickets when only scattered seats remain.

        Scenario:
        - Need 4 seats
        - Row 1: A R R A R R A R R A (4 singles: seats 1, 4, 7, 10)
        - Row 2: All RESERVED

        Expected: Return 4 scattered singles [(1,1), (1,4), (1,7), (1,10)]

        Rationale: For max 4-ticket system, scattered seats are acceptable
        when consecutive seats cannot be found.
        """
        finder: SeatFinder = SeatFinder()
        bf_key = _make_key('test_seats_bf:13:A-1')
        client = kvrocks_client.get_client()

        rows = 2
        cols = 10

        # Row 1: Create pattern with 4 scattered single seats
        # Pattern: A R R A R R A R R A
        # Singles at positions: 1, 4, 7, 10
        for seat_num in range(1, 11):
            seat_idx = (1 - 1) * cols + (seat_num - 1)  # Row 1
            if seat_num in [1, 4, 7, 10]:
                # Keep as AVAILABLE (00) - default state
                continue
            else:
                # Set to RESERVED (01)
                await _set_seat_state(client, bf_key, seat_idx, 1)

        # Row 2: Reserve all seats
        for seat_num in range(1, 11):
            seat_idx = (2 - 1) * cols + (seat_num - 1)  # Row 2
            await _set_seat_state(client, bf_key, seat_idx, 1)  # RESERVED

        # When: Try to find 4 consecutive seats
        # Reality: 4 singles exist (largest block = 1)
        result = await finder.find_consecutive_seats(
            bf_key=bf_key, rows=rows, cols=cols, quantity=4
        )

        # Then: Lua script should return the 4 scattered singles
        assert result is not None
        assert len(result) == 4

        # Verify we got the correct scattered seats
        seat_positions = [(row, seat_num) for row, seat_num, _ in result]
        assert (1, 1) in seat_positions
        assert (1, 4) in seat_positions
        assert (1, 7) in seat_positions
        assert (1, 10) in seat_positions

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_smart_fallback_3_plus_1(self):
        """
        Test smart fallback: 3 consecutive + 1 single (need 4 seats).

        Pattern: [A A A] R [A] R R R R R
        Available: Seats 1,2,3 (consecutive) + Seat 5 (single)
        Expected: Return [1,2,3,5] (largest block first, then singles)
        """
        finder: SeatFinder = SeatFinder()
        bf_key = _make_key('test_seats_bf:14:A-1')
        client = kvrocks_client.get_client()

        rows = 1
        cols = 10

        # Create pattern: A A A R A R R R R R
        # Reserve seats 4, 6, 7, 8, 9, 10
        for seat_num in [4, 6, 7, 8, 9, 10]:
            seat_idx = seat_num - 1
            await _set_seat_state(client, bf_key, seat_idx, 1)

        # When: Try to find 4 seats
        result = await finder.find_consecutive_seats(
            bf_key=bf_key, rows=rows, cols=cols, quantity=4
        )

        # Then: Should return 3+1 combination
        assert result is not None
        assert len(result) == 4

        # Verify seats (should prioritize largest block first)
        seat_nums = [seat_num for _, seat_num, _ in result]
        assert seat_nums == [1, 2, 3, 5]  # [3 consecutive] + [1 single]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_smart_fallback_2_plus_2(self):
        """
        Test smart fallback: 2 pairs (need 4 seats).

        Pattern: [A A] R R [A A] R R R R
        Available: Seats 1,2 (pair) + Seats 5,6 (pair)
        Expected: Return [1,2,5,6] (both pairs)
        """
        finder: SeatFinder = SeatFinder()
        bf_key = _make_key('test_seats_bf:15:A-1')
        client = kvrocks_client.get_client()

        rows = 1
        cols = 10

        # Create pattern: A A R R A A R R R R
        # Reserve seats 3, 4, 7, 8, 9, 10
        for seat_num in [3, 4, 7, 8, 9, 10]:
            seat_idx = seat_num - 1
            await _set_seat_state(client, bf_key, seat_idx, 1)

        # When: Try to find 4 seats
        result = await finder.find_consecutive_seats(
            bf_key=bf_key, rows=rows, cols=cols, quantity=4
        )

        # Then: Should return 2+2 combination
        assert result is not None
        assert len(result) == 4

        # Verify seats (should return both pairs, sorted by block size - both size 2)
        seat_nums = [seat_num for _, seat_num, _ in result]
        assert set(seat_nums) == {1, 2, 5, 6}

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_smart_fallback_2_plus_1_plus_1(self):
        """
        Test smart fallback: 1 pair + 2 singles (need 4 seats).

        Pattern: [A A] R [A] R [A] R R R R
        Available: Seats 1,2 (pair) + Seat 4 (single) + Seat 6 (single)
        Expected: Return [1,2,4,6] (largest block first, then singles)
        """
        finder: SeatFinder = SeatFinder()
        bf_key = _make_key('test_seats_bf:16:A-1')
        client = kvrocks_client.get_client()

        rows = 1
        cols = 10

        # Create pattern: A A R A R A R R R R
        # Reserve seats 3, 5, 7, 8, 9, 10
        for seat_num in [3, 5, 7, 8, 9, 10]:
            seat_idx = seat_num - 1
            await _set_seat_state(client, bf_key, seat_idx, 1)

        # When: Try to find 4 seats
        result = await finder.find_consecutive_seats(
            bf_key=bf_key, rows=rows, cols=cols, quantity=4
        )

        # Then: Should return 2+1+1 combination
        assert result is not None
        assert len(result) == 4

        # Verify seats (should prioritize largest block first)
        seat_nums = [seat_num for _, seat_num, _ in result]
        # First 2 should be the pair [1,2], then singles [4,6]
        assert seat_nums[:2] == [1, 2]  # Consecutive pair first
        assert set(seat_nums[2:]) == {4, 6}  # Then singles

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_smart_fallback_1_plus_1_plus_1_plus_1(self):
        """
        Test smart fallback: 4 scattered singles (need 4 seats).

        Pattern: [A] R [A] R [A] R [A] R R R
        Available: Seats 1,3,5,7 (all singles)
        Expected: Return [1,3,5,7] (all singles)
        """
        finder: SeatFinder = SeatFinder()
        bf_key = _make_key('test_seats_bf:17:A-1')
        client = kvrocks_client.get_client()

        rows = 1
        cols = 10

        # Create pattern: A R A R A R A R R R
        # Reserve seats 2, 4, 6, 8, 9, 10
        for seat_num in [2, 4, 6, 8, 9, 10]:
            seat_idx = seat_num - 1
            await _set_seat_state(client, bf_key, seat_idx, 1)

        # When: Try to find 4 seats
        result = await finder.find_consecutive_seats(
            bf_key=bf_key, rows=rows, cols=cols, quantity=4
        )

        # Then: Should return 4 scattered singles
        assert result is not None
        assert len(result) == 4

        # Verify seats (all singles, order may vary when block sizes are equal)
        seat_nums = [seat_num for _, seat_num, _ in result]
        assert set(seat_nums) == {1, 3, 5, 7}
