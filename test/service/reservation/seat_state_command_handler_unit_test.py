"""
Unit tests for seat reservation helper functions

Tests pure functions and business logic without mocking external dependencies.
Integration tests in test/service/reservation/integration/ cover the full flow.
"""

import pytest
from src.service.reservation.driven_adapter.reservation_helper.seat_finder import (
    SeatFinder,
)
from src.service.reservation.driven_adapter.seat_state_command_handler_impl import (
    SeatStateCommandHandlerImpl,
)


# ============================================================================
# Test Pure Functions - _calculate_seat_index
# ============================================================================


@pytest.mark.unit
class TestCalculateSeatIndex:
    """Test seat index calculation logic"""

    def test_first_seat_first_row(self) -> None:
        # Given: Row 1, Seat 1, 10 seats per row
        # When: Calculate index
        result = SeatFinder._calculate_seat_index(row=1, seat_num=1, cols=10)
        # Then: Should be index 0
        assert result == 0

    def test_last_seat_first_row(self) -> None:
        # Given: Row 1, Seat 10, 10 seats per row
        # When: Calculate index
        result = SeatFinder._calculate_seat_index(row=1, seat_num=10, cols=10)
        # Then: Should be index 9
        assert result == 9

    def test_first_seat_second_row(self) -> None:
        # Given: Row 2, Seat 1, 10 seats per row
        # When: Calculate index
        result = SeatFinder._calculate_seat_index(row=2, seat_num=1, cols=10)
        # Then: Should be index 10
        assert result == 10

    def test_middle_seat_middle_row(self) -> None:
        # Given: Row 3, Seat 5, 8 seats per row
        # When: Calculate index
        # Formula: (3-1) * 8 + (5-1) = 16 + 4 = 20
        result = SeatFinder._calculate_seat_index(row=3, seat_num=5, cols=8)
        # Then: Should be index 20
        assert result == 20

    def test_single_seat_per_row(self) -> None:
        # Given: Row 5, Seat 1, 1 seat per row
        # When: Calculate index
        # Formula: (5-1) * 1 + (1-1) = 4
        result = SeatFinder._calculate_seat_index(row=5, seat_num=1, cols=1)
        # Then: Should be index 4
        assert result == 4

    def test_large_venue(self) -> None:
        # Given: Row 20, Seat 50, 100 seats per row
        # When: Calculate index
        # Formula: (20-1) * 100 + (50-1) = 1900 + 49 = 1949
        result = SeatFinder._calculate_seat_index(row=20, seat_num=50, cols=100)
        # Then: Should be index 1949
        assert result == 1949


# ============================================================================
# Test Pure Functions - _error_result
# ============================================================================


@pytest.mark.unit
class TestErrorResult:
    """Test error result formatting"""

    def test_error_result_format(self) -> None:
        # Given: Error message
        message = 'Seat already reserved'
        # When: Create error result
        result = SeatStateCommandHandlerImpl._error_result(message)
        # Then: Should return standardized error format
        assert result['success'] is False
        assert result['error_message'] == 'Seat already reserved'
        assert result['reserved_seats'] == []

    def test_error_result_with_complex_message(self) -> None:
        # Given: Complex error message
        message = 'Seat 1-1 is already SOLD'
        # When: Create error result
        result = SeatStateCommandHandlerImpl._error_result(message)
        # Then: Should preserve exact message
        assert result['success'] is False
        assert result['error_message'] == 'Seat 1-1 is already SOLD'
        assert result['reserved_seats'] == []
