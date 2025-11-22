"""
Unit tests for SeatFinder

Tests consecutive seat finding logic using bitfield operations.
"""

import pytest

from src.service.seat_reservation.driven_adapter.seat_reservation_helper.seat_finder import (
    SeatFinder,
)


# =============================================================================
# Pure Unit Tests (no external dependencies)
# =============================================================================
class TestSeatFinderCalculations:
    @pytest.mark.unit
    def test_calculate_seat_index(self):
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
