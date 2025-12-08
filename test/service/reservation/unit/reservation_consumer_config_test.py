"""
Test to enforce SeatReservationConsumer configuration.

This test ensures MAX_CONCURRENT_TASKS stays at 1 to prevent race conditions.
If you need to change this, you MUST also implement atomic Lua scripts for seat reservation.
"""

from src.service.reservation.driving_adapter.reservation_mq_consumer import (
    SeatReservationConsumer,
)
import pytest


@pytest.mark.unit
class TestSeatReservationConsumerConfig:
    """Tests for SeatReservationConsumer configuration constraints."""

    def test_max_concurrent_tasks_must_be_one(self) -> None:
        """
        CRITICAL: MAX_CONCURRENT_TASKS must be 1 to prevent race conditions.

        Race condition scenario with MAX_CONCURRENT_TASKS > 1:
        1. Task 1: find_consecutive_seats() -> finds seat [1-1]
        2. Task 2: find_consecutive_seats() -> finds seat [1-1] (same seat!)
        3. Task 1: reserve seat [1-1]
        4. Task 2: reserve seat [1-1] -> DUPLICATE BOOKING!

        If you need higher concurrency, you MUST:
        1. Implement atomic find_and_reserve Lua script
        2. Or partition messages by subsection to ensure same subsection -> same partition
        """
        assert SeatReservationConsumer.MAX_CONCURRENT_TASKS == 1, (
            'MAX_CONCURRENT_TASKS must be 1 to prevent seat reservation race conditions. '
            'See test docstring for details on why this is critical.'
        )
