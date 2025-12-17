"""
Integration tests for SeatFinder

Tests consecutive seat finding logic using row_blocks metadata.
"""

import pytest

from src.platform.config.di import container
import src.platform.state.kvrocks_client as kvrocks_module


class TestSeatFinder:
    @pytest.fixture(autouse=True)
    async def setup_kvrocks(self) -> None:
        await kvrocks_module.kvrocks_client.initialize()

    @pytest.fixture
    def unique_event_id(self) -> int:
        """Generate unique event_id for each test"""
        import random
        import time

        return int(time.time() * 1000000) % 10000000 + random.randint(1, 9999)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_single_row_success(self, unique_event_id: int) -> None:
        # Given: Initialize 1 row, 5 seats, all available
        row_block_manager = container.row_block_manager()
        finder = container.seat_finder()
        event_id = unique_event_id
        rows = 1
        cols = 5

        await row_block_manager.initialize_subsection(
            event_id=event_id, section='A', subsection=1, rows=rows, cols=cols
        )

        # When: Find 3 consecutive seats
        result = await finder.find_consecutive_seats(
            rows=rows,
            cols=cols,
            quantity=3,
            event_id=event_id,
            section='A',
            subsection=1,
        )

        # Then: Should find seats 1-3 in row 1
        assert result is not None
        assert len(result) == 3
        assert result == [(1, 1, 0), (1, 2, 1), (1, 3, 2)]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_with_reserved_seats(self, unique_event_id: int) -> None:
        # Given: Setup with some seats reserved
        row_block_manager = container.row_block_manager()
        finder = container.seat_finder()
        event_id = unique_event_id
        rows = 1
        cols = 5

        await row_block_manager.initialize_subsection(
            event_id=event_id, section='A', subsection=1, rows=rows, cols=cols
        )

        # Mark seats 1-2 as reserved (remove from blocks)
        await row_block_manager.remove_seats_from_blocks(
            event_id=event_id,
            section='A',
            subsection=1,
            row=1,
            seat_indices=[0, 1],  # seats 1-2
            cols=cols,
        )

        # When: Find 2 consecutive seats
        result = await finder.find_consecutive_seats(
            rows=rows,
            cols=cols,
            quantity=2,
            event_id=event_id,
            section='A',
            subsection=1,
        )

        # Then: Should find seats 3-4
        assert result is not None
        assert len(result) == 2
        assert result == [(1, 3, 2), (1, 4, 3)]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_multiple_rows(self, unique_event_id: int) -> None:
        """Test finding consecutive seats across multiple rows"""
        # Given: Setup 2 rows, first row mostly reserved
        row_block_manager = container.row_block_manager()
        finder = container.seat_finder()
        event_id = unique_event_id
        rows = 2
        cols = 3

        await row_block_manager.initialize_subsection(
            event_id=event_id, section='A', subsection=1, rows=rows, cols=cols
        )

        # Row 1: Reserve seats 1-2
        await row_block_manager.remove_seats_from_blocks(
            event_id=event_id,
            section='A',
            subsection=1,
            row=1,
            seat_indices=[0, 1],
            cols=cols,
        )

        # When: Find 2 consecutive seats
        result = await finder.find_consecutive_seats(
            rows=rows,
            cols=cols,
            quantity=2,
            event_id=event_id,
            section='A',
            subsection=1,
        )

        # Then: Should find seats in row 2
        assert result is not None
        assert len(result) == 2
        assert result == [(2, 1, 3), (2, 2, 4)]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_but_scattered_seats_exist(
        self, unique_event_id: int
    ) -> None:
        """Test when no consecutive seats available but scattered seats exist"""
        # Given: Setup seats with gaps (no consecutive pairs)
        row_block_manager = container.row_block_manager()
        finder = container.seat_finder()
        event_id = unique_event_id
        rows = 1
        cols = 5

        await row_block_manager.initialize_subsection(
            event_id=event_id, section='A', subsection=1, rows=rows, cols=cols
        )

        # Pattern: A R A R A (reserve seats 2 and 4)
        await row_block_manager.remove_seats_from_blocks(
            event_id=event_id,
            section='A',
            subsection=1,
            row=1,
            seat_indices=[1, 3],  # seats 2 and 4
            cols=cols,
        )

        # When: Try to find 2 consecutive seats
        result = await finder.find_consecutive_seats(
            rows=rows,
            cols=cols,
            quantity=2,
            event_id=event_id,
            section='A',
            subsection=1,
        )

        # Then: Should return 2 scattered singles from available seats {1, 3, 5}
        assert result is not None
        assert len(result) == 2
        # Available seats are 1, 3, 5 (indices 0, 2, 4) - order may vary
        available_indices = {0, 2, 4}
        for row, _seat_num, seat_idx in result:
            assert row == 1
            assert seat_idx in available_indices

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_exact_match(self, unique_event_id: int) -> None:
        # Given: Setup with exactly N consecutive available seats
        row_block_manager = container.row_block_manager()
        finder = container.seat_finder()
        event_id = unique_event_id
        rows = 1
        cols = 3

        await row_block_manager.initialize_subsection(
            event_id=event_id, section='A', subsection=1, rows=rows, cols=cols
        )

        # When: Find exactly 3 consecutive seats
        result = await finder.find_consecutive_seats(
            rows=rows,
            cols=cols,
            quantity=3,
            event_id=event_id,
            section='A',
            subsection=1,
        )

        # Then: Should find all seats
        assert result is not None
        assert len(result) == 3
        assert result == [(1, 1, 0), (1, 2, 1), (1, 3, 2)]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_skip_sold_seats(self, unique_event_id: int) -> None:
        # Given: Setup with SOLD seats
        row_block_manager = container.row_block_manager()
        finder = container.seat_finder()
        event_id = unique_event_id
        rows = 1
        cols = 5

        await row_block_manager.initialize_subsection(
            event_id=event_id, section='A', subsection=1, rows=rows, cols=cols
        )

        # Mark seat 2 as sold (remove from blocks)
        await row_block_manager.remove_seats_from_blocks(
            event_id=event_id,
            section='A',
            subsection=1,
            row=1,
            seat_indices=[1],  # seat 2
            cols=cols,
        )

        # When: Find 3 consecutive seats
        result = await finder.find_consecutive_seats(
            rows=rows,
            cols=cols,
            quantity=3,
            event_id=event_id,
            section='A',
            subsection=1,
        )

        # Then: Should find seats 3-5
        assert result is not None
        assert len(result) == 3
        assert result == [(1, 3, 2), (1, 4, 3), (1, 5, 4)]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_finds_earliest_available(
        self, unique_event_id: int
    ) -> None:
        # Given: Multiple consecutive groups available
        row_block_manager = container.row_block_manager()
        finder = container.seat_finder()
        event_id = unique_event_id
        rows = 2
        cols = 4

        await row_block_manager.initialize_subsection(
            event_id=event_id, section='A', subsection=1, rows=rows, cols=cols
        )

        # Row 1: R R A A (reserve seats 1-2)
        await row_block_manager.remove_seats_from_blocks(
            event_id=event_id,
            section='A',
            subsection=1,
            row=1,
            seat_indices=[0, 1],
            cols=cols,
        )

        # When: Find 2 consecutive seats
        result = await finder.find_consecutive_seats(
            rows=rows,
            cols=cols,
            quantity=2,
            event_id=event_id,
            section='A',
            subsection=1,
        )

        # Then: Should find row 1, seats 3-4 (earliest)
        assert result is not None
        assert len(result) == 2
        assert result == [(1, 3, 2), (1, 4, 3)]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_quantity_one(self, unique_event_id: int) -> None:
        # Given: Setup with some reserved seats
        row_block_manager = container.row_block_manager()
        finder = container.seat_finder()
        event_id = unique_event_id
        rows = 1
        cols = 3

        await row_block_manager.initialize_subsection(
            event_id=event_id, section='A', subsection=1, rows=rows, cols=cols
        )

        # Reserve seat 1
        await row_block_manager.remove_seats_from_blocks(
            event_id=event_id,
            section='A',
            subsection=1,
            row=1,
            seat_indices=[0],
            cols=cols,
        )

        # When: Find 1 seat
        result = await finder.find_consecutive_seats(
            rows=rows,
            cols=cols,
            quantity=1,
            event_id=event_id,
            section='A',
            subsection=1,
        )

        # Then: Should find seat 2
        assert result is not None
        assert len(result) == 1
        assert result == [(1, 2, 1)]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_empty_venue(self, unique_event_id: int) -> None:
        # Given: Empty venue (all seats available)
        row_block_manager = container.row_block_manager()
        finder = container.seat_finder()
        event_id = unique_event_id
        rows = 3
        cols = 10

        await row_block_manager.initialize_subsection(
            event_id=event_id, section='A', subsection=1, rows=rows, cols=cols
        )

        # When: Find 4 consecutive seats
        result = await finder.find_consecutive_seats(
            rows=rows,
            cols=cols,
            quantity=4,
            event_id=event_id,
            section='A',
            subsection=1,
        )

        # Then: Should find first 4 seats in row 1
        assert result is not None
        assert len(result) == 4
        expected = [(1, i + 1, i) for i in range(4)]
        assert result == expected

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_full_venue(self, unique_event_id: int) -> None:
        # Given: All seats reserved
        row_block_manager = container.row_block_manager()
        finder = container.seat_finder()
        event_id = unique_event_id
        rows = 2
        cols = 3

        await row_block_manager.initialize_subsection(
            event_id=event_id, section='A', subsection=1, rows=rows, cols=cols
        )

        # Reserve all seats in both rows
        for row in range(1, rows + 1):
            await row_block_manager.remove_seats_from_blocks(
                event_id=event_id,
                section='A',
                subsection=1,
                row=row,
                seat_indices=list(range(cols)),
                cols=cols,
            )

        # When: Try to find consecutive seats
        result = await finder.find_consecutive_seats(
            rows=rows,
            cols=cols,
            quantity=2,
            event_id=event_id,
            section='A',
            subsection=1,
        )

        # Then: Should return None
        assert result is None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_consecutive_seats_smart_fallback(self, unique_event_id: int) -> None:
        """
        Test smart fallback: Return largest consecutive blocks when perfect consecutive not found.
        """
        row_block_manager = container.row_block_manager()
        finder = container.seat_finder()
        event_id = unique_event_id
        rows = 3
        cols = 5

        await row_block_manager.initialize_subsection(
            event_id=event_id, section='A', subsection=1, rows=rows, cols=cols
        )

        # Row 1: Reserve seats 1, 4, 5 → leaves seats 2-3 available
        await row_block_manager.remove_seats_from_blocks(
            event_id=event_id,
            section='A',
            subsection=1,
            row=1,
            seat_indices=[0, 3, 4],
            cols=cols,
        )

        # Row 2: Reserve seats 3-5 → leaves seats 1-2 available
        await row_block_manager.remove_seats_from_blocks(
            event_id=event_id,
            section='A',
            subsection=1,
            row=2,
            seat_indices=[2, 3, 4],
            cols=cols,
        )

        # Row 3: Reserve all seats
        await row_block_manager.remove_seats_from_blocks(
            event_id=event_id,
            section='A',
            subsection=1,
            row=3,
            seat_indices=list(range(cols)),
            cols=cols,
        )

        # When: Find 4 consecutive seats
        result = await finder.find_consecutive_seats(
            rows=rows,
            cols=cols,
            quantity=4,
            event_id=event_id,
            section='A',
            subsection=1,
        )

        # Then: Should return 4 seats from available blocks (order may vary)
        assert result is not None
        assert len(result) == 4

        # Expected seats: Row 1 (seats 2-3) + Row 2 (seats 1-2), order may vary
        expected_seats = {(1, 2, 1), (1, 3, 2), (2, 1, 5), (2, 2, 6)}
        actual_seats = set(result)
        assert actual_seats == expected_seats

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_smart_fallback_3_plus_1(self, unique_event_id: int) -> None:
        """
        Test smart fallback: 3 consecutive + 1 single (need 4 seats).
        """
        row_block_manager = container.row_block_manager()
        finder = container.seat_finder()
        event_id = unique_event_id
        rows = 1
        cols = 10

        await row_block_manager.initialize_subsection(
            event_id=event_id, section='A', subsection=1, rows=rows, cols=cols
        )

        # Reserve seats 4, 6, 7, 8, 9, 10 → leaves 1,2,3,5 available
        await row_block_manager.remove_seats_from_blocks(
            event_id=event_id,
            section='A',
            subsection=1,
            row=1,
            seat_indices=[3, 5, 6, 7, 8, 9],
            cols=cols,
        )

        # When: Try to find 4 seats
        result = await finder.find_consecutive_seats(
            rows=rows,
            cols=cols,
            quantity=4,
            event_id=event_id,
            section='A',
            subsection=1,
        )

        # Then: Should return 3+1 combination
        assert result is not None
        assert len(result) == 4

        seat_nums = [seat_num for _, seat_num, _ in result]
        assert seat_nums == [1, 2, 3, 5]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_smart_fallback_2_plus_2(self, unique_event_id: int) -> None:
        """
        Test smart fallback: 2 pairs (need 4 seats).
        """
        row_block_manager = container.row_block_manager()
        finder = container.seat_finder()
        event_id = unique_event_id
        rows = 1
        cols = 10

        await row_block_manager.initialize_subsection(
            event_id=event_id, section='A', subsection=1, rows=rows, cols=cols
        )

        # Reserve seats 3, 4, 7, 8, 9, 10 → leaves 1,2,5,6 available
        await row_block_manager.remove_seats_from_blocks(
            event_id=event_id,
            section='A',
            subsection=1,
            row=1,
            seat_indices=[2, 3, 6, 7, 8, 9],
            cols=cols,
        )

        # When: Try to find 4 seats
        result = await finder.find_consecutive_seats(
            rows=rows,
            cols=cols,
            quantity=4,
            event_id=event_id,
            section='A',
            subsection=1,
        )

        # Then: Should return 2+2 combination
        assert result is not None
        assert len(result) == 4

        seat_nums = [seat_num for _, seat_num, _ in result]
        assert set(seat_nums) == {1, 2, 5, 6}

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_smart_fallback_2_plus_1_plus_1(self, unique_event_id: int) -> None:
        """
        Test smart fallback: 1 pair + 2 singles (need 4 seats).
        """
        row_block_manager = container.row_block_manager()
        finder = container.seat_finder()
        event_id = unique_event_id
        rows = 1
        cols = 10

        await row_block_manager.initialize_subsection(
            event_id=event_id, section='A', subsection=1, rows=rows, cols=cols
        )

        # Reserve seats 3, 5, 7, 8, 9, 10 → leaves 1,2,4,6 available
        await row_block_manager.remove_seats_from_blocks(
            event_id=event_id,
            section='A',
            subsection=1,
            row=1,
            seat_indices=[2, 4, 6, 7, 8, 9],
            cols=cols,
        )

        # When: Try to find 4 seats
        result = await finder.find_consecutive_seats(
            rows=rows,
            cols=cols,
            quantity=4,
            event_id=event_id,
            section='A',
            subsection=1,
        )

        # Then: Should return 2+1+1 combination
        assert result is not None
        assert len(result) == 4

        seat_nums = [seat_num for _, seat_num, _ in result]
        # First 2 should be the pair [1,2], then singles
        assert seat_nums[:2] == [1, 2]
        assert set(seat_nums[2:]) == {4, 6}

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_smart_fallback_1_plus_1_plus_1_plus_1(self, unique_event_id: int) -> None:
        """
        Test smart fallback: 4 scattered singles (need 4 seats).
        """
        row_block_manager = container.row_block_manager()
        finder = container.seat_finder()
        event_id = unique_event_id
        rows = 1
        cols = 10

        await row_block_manager.initialize_subsection(
            event_id=event_id, section='A', subsection=1, rows=rows, cols=cols
        )

        # Reserve seats 2, 4, 6, 8, 9, 10 → leaves 1,3,5,7 available
        await row_block_manager.remove_seats_from_blocks(
            event_id=event_id,
            section='A',
            subsection=1,
            row=1,
            seat_indices=[1, 3, 5, 7, 8, 9],
            cols=cols,
        )

        # When: Try to find 4 seats
        result = await finder.find_consecutive_seats(
            rows=rows,
            cols=cols,
            quantity=4,
            event_id=event_id,
            section='A',
            subsection=1,
        )

        # Then: Should return 4 scattered singles
        assert result is not None
        assert len(result) == 4

        seat_nums = [seat_num for _, seat_num, _ in result]
        assert set(seat_nums) == {1, 3, 5, 7}
