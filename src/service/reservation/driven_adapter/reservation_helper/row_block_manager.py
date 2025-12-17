"""
Row Block Manager

Manages row-level consecutive seat blocks metadata for fast seat finding.

Storage Format:
    Key: row_blocks:{event_id}:{section}-{subsection}
    Type: Hash
    Fields: row_number -> JSON array of [start, end] blocks

Example:
    row_blocks:1:A-1 = {
        "1": "[[0,4],[10,14]]",      # Row 1: 2 blocks (seats 0-4, 10-14)
        "2": "[]",                    # Row 2: no available seats
        "3": "[[0,19]]",              # Row 3: all 20 seats available
    }
"""

from collections.abc import Awaitable
import os
from typing import Optional, cast

import orjson

from src.platform.logging.loguru_io import Logger
from src.platform.state.kvrocks_client import KvrocksClient


def _get_key_prefix() -> str:
    """Get key prefix dynamically from environment for test isolation."""
    return os.getenv('KVROCKS_KEY_PREFIX', '')


def _make_key(key: str) -> str:
    """Add prefix to key for test isolation"""
    return f'{_get_key_prefix()}{key}'


class RowBlockManager:
    """
    Manages row-level consecutive seat blocks for O(1) seat finding.

    Trade-off:
    - Query: O(1) network + O(rows) Python processing
    - Write: Need to update blocks on every reservation/release
    """

    def __init__(self, *, kvrocks_client: KvrocksClient) -> None:
        self._kvrocks_client = kvrocks_client

    @staticmethod
    def _blocks_key(*, event_id: int, section: str, subsection: int) -> str:
        return _make_key(f'row_blocks:{event_id}:{section}-{subsection}')

    @staticmethod
    def _compute_blocks_from_statuses(seat_statuses: list[int]) -> list[list[int]]:
        """
        Compute consecutive available blocks from seat status array.

        Args:
            seat_statuses: List of seat statuses (0=AVAILABLE, 1=RESERVED, 2=SOLD)

        Returns:
            List of [start, end] blocks (inclusive indices)
        """
        blocks: list[list[int]] = []
        start: Optional[int] = None

        for i, status in enumerate(seat_statuses):
            if status == 0:  # AVAILABLE
                if start is None:
                    start = i
            else:
                if start is not None:
                    blocks.append([start, i - 1])
                    start = None

        # Don't forget the last block
        if start is not None:
            blocks.append([start, len(seat_statuses) - 1])

        return blocks

    async def initialize_subsection(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        rows: int,
        cols: int,
    ) -> None:
        """
        Initialize row blocks for a new subsection (all seats available).

        Args:
            event_id: Event ID
            section: Section name
            subsection: Subsection number
            rows: Number of rows
            cols: Seats per row
        """
        client = self._kvrocks_client.get_client()
        key = self._blocks_key(event_id=event_id, section=section, subsection=subsection)

        # All seats available = one block per row covering all seats
        full_row_block = orjson.dumps([[0, cols - 1]]).decode()

        # Use pipeline for batch write
        async with client.pipeline() as pipe:
            for row in range(1, rows + 1):
                pipe.hset(key, str(row), full_row_block)
            await pipe.execute()

        Logger.base.info(
            f'[ROW-BLOCKS] Initialized {rows} rows for {section}-{subsection} | key={key}'
        )

    async def get_all_blocks(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
    ) -> dict[int, list[list[int]]]:
        """
        Returns:
            Dict mapping row number to list of [start, end] blocks
        """
        client = self._kvrocks_client.get_client()
        key = self._blocks_key(event_id=event_id, section=section, subsection=subsection)

        raw_data = await cast(Awaitable[dict[bytes, bytes]], client.hgetall(key))

        result: dict[int, list[list[int]]] = {}
        for row_bytes, blocks_bytes in raw_data.items():
            row = int(row_bytes.decode() if isinstance(row_bytes, bytes) else row_bytes)
            blocks_str = blocks_bytes.decode() if isinstance(blocks_bytes, bytes) else blocks_bytes
            result[row] = orjson.loads(blocks_str)

        return result

    async def update_row_blocks(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        row: int,
        new_blocks: list[list[int]],
    ) -> None:
        """
        Update blocks for a single row.

        Args:
            event_id: Event ID
            section: Section name
            subsection: Subsection number
            row: Row number (1-indexed)
            new_blocks: New list of [start, end] blocks
        """
        client = self._kvrocks_client.get_client()
        key = self._blocks_key(event_id=event_id, section=section, subsection=subsection)

        await cast(Awaitable[int], client.hset(key, str(row), orjson.dumps(new_blocks).decode()))

    async def remove_seats_from_blocks(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        row: int,
        seat_indices: list[int],
        cols: int,
    ) -> list[list[int]]:
        """
        Remove reserved seats from row blocks.

        Args:
            event_id: Event ID
            section: Section name
            subsection: Subsection number
            row: Row number
            seat_indices: List of seat indices within the row (0-indexed)
            cols: Total seats per row

        Returns:
            Updated blocks for this row
        """
        client = self._kvrocks_client.get_client()
        key = self._blocks_key(event_id=event_id, section=section, subsection=subsection)

        # Get current blocks for this row
        raw = await cast(Awaitable[bytes | None], client.hget(key, str(row)))
        if not raw:
            return []

        current_blocks: list[list[int]] = orjson.loads(
            raw.decode() if isinstance(raw, bytes) else raw
        )

        # Convert blocks to a set of available seats
        available = set()
        for start, end in current_blocks:
            available.update(range(start, end + 1))

        # Remove reserved seats
        for idx in seat_indices:
            available.discard(idx)

        # Rebuild blocks from remaining available seats
        sorted_available = sorted(available)
        new_blocks = self._rebuild_blocks(sorted_available)

        # Save updated blocks
        await cast(Awaitable[int], client.hset(key, str(row), orjson.dumps(new_blocks).decode()))

        return new_blocks

    async def add_seats_to_blocks(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        row: int,
        seat_indices: list[int],
    ) -> list[list[int]]:
        """
        Add released seats back to row blocks.

        Args:
            event_id: Event ID
            section: Section name
            subsection: Subsection number
            row: Row number
            seat_indices: List of seat indices within the row (0-indexed)

        Returns:
            Updated blocks for this row
        """
        client = self._kvrocks_client.get_client()
        key = self._blocks_key(event_id=event_id, section=section, subsection=subsection)

        # Get current blocks for this row
        raw = await cast(Awaitable[bytes | None], client.hget(key, str(row)))
        current_blocks: list[list[int]] = []
        if raw:
            current_blocks = orjson.loads(raw.decode() if isinstance(raw, bytes) else raw)

        # Convert blocks to a set of available seats
        available = set()
        for start, end in current_blocks:
            available.update(range(start, end + 1))

        # Add released seats
        available.update(seat_indices)

        # Rebuild blocks from all available seats
        sorted_available = sorted(available)
        new_blocks = self._rebuild_blocks(sorted_available)

        # Save updated blocks
        await cast(Awaitable[int], client.hset(key, str(row), orjson.dumps(new_blocks).decode()))

        return new_blocks

    @staticmethod
    def _rebuild_blocks(sorted_seats: list[int]) -> list[list[int]]:
        """
        Rebuild consecutive blocks from sorted seat indices.

        Args:
            sorted_seats: Sorted list of available seat indices

        Returns:
            List of [start, end] blocks

        Examples:
            [0,1,2,3,4]    → [[0,4]]                      # all consecutive
            [3]            → [[3,3]]                      # single seat
            [0,1,3,4]      → [[0,1],[3,4]]                # gap in middle
            [0,2,4,6]      → [[0,0],[2,2],[4,4],[6,6]]    # all isolated
            []             → []                           # empty
            [0,1,2,5,6,10] → [[0,2],[5,6],[10,10]]        # mixed pattern
        """
        if not sorted_seats:
            return []

        blocks: list[list[int]] = []
        start = sorted_seats[0]
        prev = start

        for seat in sorted_seats[1:]:
            if seat == prev + 1:
                prev = seat
            else:
                blocks.append([start, prev])
                start = seat
                prev = seat

        blocks.append([start, prev])
        return blocks

    async def find_consecutive_seats(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        quantity: int,
        rows: int,
        cols: int,
    ) -> Optional[list[tuple[int, int, int]]]:
        """
        Find consecutive available seats using row blocks.

        Strategy:
        1. Priority 1: Find N consecutive seats in one block (best UX)
        2. Priority 2: Combine largest blocks to reach quantity (fallback)

        Args:
            event_id: Event ID
            section: Section name
            subsection: Subsection number
            quantity: Number of seats needed
            rows: Total rows
            cols: Seats per row

        Returns:
            List of (row, seat_num, seat_index) tuples, or None if not enough seats
        """
        all_blocks = await self.get_all_blocks(
            event_id=event_id,
            section=section,
            subsection=subsection,
        )

        # Collect all blocks with metadata for sorting
        all_block_info: list[tuple[int, int, int, int]] = []  # (size, row, start, end)

        # Priority 1: Find perfect consecutive block
        for row in range(1, rows + 1):
            blocks = all_blocks.get(row, [])
            for start, end in blocks:
                block_size = end - start + 1
                if block_size >= quantity:
                    # Found! Return first N seats from this block
                    return [
                        (row, start + i + 1, (row - 1) * cols + start + i) for i in range(quantity)
                    ]
                all_block_info.append((block_size, row, start, end))

        # Priority 2: Fallback - combine largest blocks
        if all_block_info:
            # Sort by block size descending
            all_block_info.sort(reverse=True)

            result: list[tuple[int, int, int]] = []
            for _size, row, start, end in all_block_info:
                for i in range(start, end + 1):
                    seat_num = i + 1  # 1-indexed
                    seat_index = (row - 1) * cols + i
                    result.append((row, seat_num, seat_index))
                    if len(result) == quantity:
                        return result

        # Not enough seats available
        Logger.base.warning(
            f'[ROW-BLOCKS] Not enough seats: need {quantity}, '
            f'section={section}, subsection={subsection}'
        )
        return None
