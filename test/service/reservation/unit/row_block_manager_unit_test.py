"""
Unit tests for RowBlockManager

Tests row-level consecutive seat block management logic.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.service.reservation.driven_adapter.reservation_helper import row_block_manager
from src.service.reservation.driven_adapter.reservation_helper.row_block_manager import (
    RowBlockManager,
)


# Use module name to avoid hardcoding paths in patch()
_MODULE = row_block_manager.__name__


# =============================================================================
# Pure Unit Tests (no external dependencies)
# =============================================================================
class TestComputeBlocksFromStatuses:
    """Test _compute_blocks_from_statuses static method"""

    @pytest.mark.unit
    def test_all_available(self) -> None:
        """All seats available = one block covering all seats"""
        statuses = [0, 0, 0, 0, 0]  # 5 available seats
        blocks = RowBlockManager._compute_blocks_from_statuses(statuses)
        assert blocks == [[0, 4]]

    @pytest.mark.unit
    def test_all_reserved(self) -> None:
        """All seats reserved = no blocks"""
        statuses = [1, 1, 1, 1, 1]  # 5 reserved seats
        blocks = RowBlockManager._compute_blocks_from_statuses(statuses)
        assert blocks == []

    @pytest.mark.unit
    def test_mixed_single_block(self) -> None:
        """Reserved at start, available at end"""
        statuses = [1, 1, 0, 0, 0]  # 2 reserved, 3 available
        blocks = RowBlockManager._compute_blocks_from_statuses(statuses)
        assert blocks == [[2, 4]]

    @pytest.mark.unit
    def test_mixed_multiple_blocks(self) -> None:
        """Available seats split by reserved seat"""
        statuses = [0, 0, 1, 0, 0]  # available, reserved, available
        blocks = RowBlockManager._compute_blocks_from_statuses(statuses)
        assert blocks == [[0, 1], [3, 4]]

    @pytest.mark.unit
    def test_alternating(self) -> None:
        """Alternating available and reserved"""
        statuses = [0, 1, 0, 1, 0]
        blocks = RowBlockManager._compute_blocks_from_statuses(statuses)
        assert blocks == [[0, 0], [2, 2], [4, 4]]

    @pytest.mark.unit
    def test_sold_seats(self) -> None:
        """Sold seats (status=2) should not be available"""
        statuses = [0, 2, 0, 0, 2]  # available, sold, available, available, sold
        blocks = RowBlockManager._compute_blocks_from_statuses(statuses)
        assert blocks == [[0, 0], [2, 3]]

    @pytest.mark.unit
    def test_empty_row(self) -> None:
        """Empty row"""
        statuses: list[int] = []
        blocks = RowBlockManager._compute_blocks_from_statuses(statuses)
        assert blocks == []


class TestRebuildBlocks:
    """Test _rebuild_blocks static method"""

    @pytest.mark.unit
    def test_consecutive_seats(self) -> None:
        """Consecutive seat indices form one block"""
        sorted_seats = [0, 1, 2, 3, 4]
        blocks = RowBlockManager._rebuild_blocks(sorted_seats)
        assert blocks == [[0, 4]]

    @pytest.mark.unit
    def test_single_seat(self) -> None:
        """Single seat forms one block"""
        sorted_seats = [3]
        blocks = RowBlockManager._rebuild_blocks(sorted_seats)
        assert blocks == [[3, 3]]

    @pytest.mark.unit
    def test_gap_in_middle(self) -> None:
        """Gap creates two blocks"""
        sorted_seats = [0, 1, 3, 4]  # gap at index 2
        blocks = RowBlockManager._rebuild_blocks(sorted_seats)
        assert blocks == [[0, 1], [3, 4]]

    @pytest.mark.unit
    def test_multiple_gaps(self) -> None:
        """Multiple gaps create multiple blocks"""
        sorted_seats = [0, 2, 4, 6]  # all isolated
        blocks = RowBlockManager._rebuild_blocks(sorted_seats)
        assert blocks == [[0, 0], [2, 2], [4, 4], [6, 6]]

    @pytest.mark.unit
    def test_empty_list(self) -> None:
        """Empty list returns empty blocks"""
        sorted_seats: list[int] = []
        blocks = RowBlockManager._rebuild_blocks(sorted_seats)
        assert blocks == []

    @pytest.mark.unit
    def test_complex_pattern(self) -> None:
        """Complex pattern with mixed consecutive and isolated seats"""
        sorted_seats = [0, 1, 2, 5, 6, 10]  # block [0-2], block [5-6], isolated [10]
        blocks = RowBlockManager._rebuild_blocks(sorted_seats)
        assert blocks == [[0, 2], [5, 6], [10, 10]]


class TestBlocksKey:
    """Test _blocks_key static method"""

    @pytest.mark.unit
    def test_key_format(self) -> None:
        """Key follows expected format"""
        with patch(f'{_MODULE}._KEY_PREFIX', ''):
            key = RowBlockManager._blocks_key(event_id=1, section='A', subsection=5)
            assert key == 'row_blocks:1:A-5'

    @pytest.mark.unit
    def test_key_with_prefix(self) -> None:
        """Key includes prefix when set"""
        with patch(f'{_MODULE}._KEY_PREFIX', 'test:'):
            key = RowBlockManager._blocks_key(event_id=42, section='B', subsection=3)
            assert key == 'test:row_blocks:42:B-3'


# =============================================================================
# Async Tests with Mocks
# =============================================================================
class TestFindConsecutiveSeats:
    """Test find_consecutive_seats method with mocked get_all_blocks"""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_find_exact_consecutive_block(self) -> None:
        """Find seats when exact consecutive block exists"""
        manager = RowBlockManager()

        # Mock get_all_blocks to return a row with 5 consecutive seats
        with patch.object(
            manager, RowBlockManager.get_all_blocks.__name__, new_callable=AsyncMock
        ) as mock:
            mock.return_value = {
                1: [[0, 4]],  # Row 1: seats 0-4 available
                2: [],  # Row 2: no seats
            }

            result = await manager.find_consecutive_seats(
                event_id=1,
                section='A',
                subsection=1,
                quantity=3,
                rows=2,
                cols=5,
            )

            # Should return first 3 seats from row 1
            assert result is not None
            assert len(result) == 3
            # (row, seat_num, seat_index)
            assert result[0] == (1, 1, 0)  # row 1, seat 1, index 0
            assert result[1] == (1, 2, 1)  # row 1, seat 2, index 1
            assert result[2] == (1, 3, 2)  # row 1, seat 3, index 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_find_in_later_row(self) -> None:
        """Find seats in later row when first row doesn't have enough"""
        manager = RowBlockManager()

        with patch.object(
            manager, RowBlockManager.get_all_blocks.__name__, new_callable=AsyncMock
        ) as mock:
            mock.return_value = {
                1: [[0, 1]],  # Row 1: only 2 seats
                2: [[0, 4]],  # Row 2: 5 seats available
            }

            result = await manager.find_consecutive_seats(
                event_id=1,
                section='A',
                subsection=1,
                quantity=4,
                rows=2,
                cols=5,
            )

            # Should return 4 seats from row 2
            assert result is not None
            assert len(result) == 4
            assert result[0] == (2, 1, 5)  # row 2, seat 1, index 5

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fallback_combine_blocks(self) -> None:
        """Fallback to combining blocks when no single block is large enough"""
        manager = RowBlockManager()

        with patch.object(
            manager, RowBlockManager.get_all_blocks.__name__, new_callable=AsyncMock
        ) as mock:
            mock.return_value = {
                1: [[0, 1]],  # Row 1: 2 seats
                2: [[2, 4]],  # Row 2: 3 seats
            }

            result = await manager.find_consecutive_seats(
                event_id=1,
                section='A',
                subsection=1,
                quantity=4,
                rows=2,
                cols=5,
            )

            # Should combine largest blocks: 3 from row 2 + 1 from row 1
            assert result is not None
            assert len(result) == 4

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_not_enough_seats(self) -> None:
        """Return None when not enough seats available"""
        manager = RowBlockManager()

        with patch.object(
            manager, RowBlockManager.get_all_blocks.__name__, new_callable=AsyncMock
        ) as mock:
            mock.return_value = {
                1: [[0, 1]],  # Only 2 seats total
            }

            result = await manager.find_consecutive_seats(
                event_id=1,
                section='A',
                subsection=1,
                quantity=5,
                rows=1,
                cols=5,
            )

            assert result is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_empty_blocks(self) -> None:
        """Return None when all blocks are empty"""
        manager = RowBlockManager()

        with patch.object(
            manager, RowBlockManager.get_all_blocks.__name__, new_callable=AsyncMock
        ) as mock:
            mock.return_value = {
                1: [],
                2: [],
            }

            result = await manager.find_consecutive_seats(
                event_id=1,
                section='A',
                subsection=1,
                quantity=1,
                rows=2,
                cols=5,
            )

            assert result is None


class TestInitializeSubsection:
    """Test initialize_subsection method"""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_initialize_creates_full_blocks(self) -> None:
        """Initialize creates full row blocks for all rows"""
        manager = RowBlockManager()

        mock_client = MagicMock()
        mock_pipe = MagicMock()  # Use MagicMock for sync methods like hset
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=None)
        mock_pipe.execute = AsyncMock()  # Only execute is async
        mock_client.pipeline.return_value = mock_pipe

        with patch(f'{_MODULE}.kvrocks_client') as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_client

            await manager.initialize_subsection(
                event_id=1,
                section='A',
                subsection=1,
                rows=3,
                cols=5,
            )

            # Verify pipeline was used
            mock_client.pipeline.assert_called_once()

            # Verify hset was called for each row with full block [[0, 4]]
            assert mock_pipe.hset.call_count == 3
            # Each call should set the full block for that row
            expected_block = '[[0,4]]'  # All 5 seats available (0-4)
            for call in mock_pipe.hset.call_args_list:
                assert call[0][2] == expected_block


class TestRemoveSeatsFromBlocks:
    """Test remove_seats_from_blocks method"""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_remove_middle_seats(self) -> None:
        """Removing middle seats splits block"""
        manager = RowBlockManager()

        mock_client = AsyncMock()
        mock_client.hget.return_value = b'[[0,4]]'  # Full row available

        with patch(f'{_MODULE}.kvrocks_client') as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_client

            result = await manager.remove_seats_from_blocks(
                event_id=1,
                section='A',
                subsection=1,
                row=1,
                seat_indices=[2],  # Remove seat at index 2
                cols=5,
            )

            # Should split into two blocks: [0,1] and [3,4]
            assert result == [[0, 1], [3, 4]]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_remove_consecutive_seats(self) -> None:
        """Removing consecutive seats shrinks block"""
        manager = RowBlockManager()

        mock_client = AsyncMock()
        mock_client.hget.return_value = b'[[0,4]]'

        with patch(f'{_MODULE}.kvrocks_client') as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_client

            result = await manager.remove_seats_from_blocks(
                event_id=1,
                section='A',
                subsection=1,
                row=1,
                seat_indices=[0, 1],  # Remove first 2 seats
                cols=5,
            )

            # Should leave block [2,4]
            assert result == [[2, 4]]


class TestAddSeatsToBlocks:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_add_seats_merges_blocks(self) -> None:
        """Adding seats can merge separate blocks"""
        manager = RowBlockManager()

        mock_client = AsyncMock()
        mock_client.hget.return_value = b'[[0,1],[3,4]]'  # Gap at index 2

        with patch(f'{_MODULE}.kvrocks_client') as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_client

            result = await manager.add_seats_to_blocks(
                event_id=1,
                section='A',
                subsection=1,
                row=1,
                seat_indices=[2],  # Add seat at index 2 (fills gap)
            )

            # Should merge into one block [0,4]
            assert result == [[0, 4]]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_add_seats_to_empty(self) -> None:
        """Adding seats to empty row creates new block"""
        manager = RowBlockManager()

        mock_client = AsyncMock()
        mock_client.hget.return_value = b'[]'  # No seats available

        with patch(f'{_MODULE}.kvrocks_client') as mock_kvrocks:
            mock_kvrocks.get_client.return_value = mock_client

            result = await manager.add_seats_to_blocks(
                event_id=1,
                section='A',
                subsection=1,
                row=1,
                seat_indices=[2, 3],
            )

            # Should create block [2,3]
            assert result == [[2, 3]]
