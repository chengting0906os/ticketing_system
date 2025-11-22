"""
Unit tests for seat reservation helper functions

Tests pure functions and business logic without mocking external dependencies.
Integration tests in test/service/seat_reservation/integration/ cover the full flow.
"""

from unittest.mock import Mock

import pytest

from src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl import (
    SeatStateCommandHandlerImpl,
)


# ============================================================================
# Test Pure Functions - _calculate_seat_index
# ============================================================================


@pytest.mark.unit
class TestCalculateSeatIndex:
    """Test seat index calculation logic"""

    def test_first_seat_first_row(self):
        # Given: Row 1, Seat 1, 10 seats per row
        # When: Calculate index
        result = SeatStateCommandHandlerImpl._calculate_seat_index(
            row=1, seat_num=1, seats_per_row=10
        )
        # Then: Should be index 0
        assert result == 0

    def test_last_seat_first_row(self):
        # Given: Row 1, Seat 10, 10 seats per row
        # When: Calculate index
        result = SeatStateCommandHandlerImpl._calculate_seat_index(
            row=1, seat_num=10, seats_per_row=10
        )
        # Then: Should be index 9
        assert result == 9

    def test_first_seat_second_row(self):
        # Given: Row 2, Seat 1, 10 seats per row
        # When: Calculate index
        result = SeatStateCommandHandlerImpl._calculate_seat_index(
            row=2, seat_num=1, seats_per_row=10
        )
        # Then: Should be index 10
        assert result == 10

    def test_middle_seat_middle_row(self):
        # Given: Row 3, Seat 5, 8 seats per row
        # When: Calculate index
        # Formula: (3-1) * 8 + (5-1) = 16 + 4 = 20
        result = SeatStateCommandHandlerImpl._calculate_seat_index(
            row=3, seat_num=5, seats_per_row=8
        )
        # Then: Should be index 20
        assert result == 20

    def test_single_seat_per_row(self):
        # Given: Row 5, Seat 1, 1 seat per row
        # When: Calculate index
        # Formula: (5-1) * 1 + (1-1) = 4
        result = SeatStateCommandHandlerImpl._calculate_seat_index(
            row=5, seat_num=1, seats_per_row=1
        )
        # Then: Should be index 4
        assert result == 4

    def test_large_venue(self):
        # Given: Row 20, Seat 50, 100 seats per row
        # When: Calculate index
        # Formula: (20-1) * 100 + (50-1) = 1900 + 49 = 1949
        result = SeatStateCommandHandlerImpl._calculate_seat_index(
            row=20, seat_num=50, seats_per_row=100
        )
        # Then: Should be index 1949
        assert result == 1949


# ============================================================================
# Test Pure Functions - _error_result
# ============================================================================


@pytest.mark.unit
class TestErrorResult:
    """Test error result formatting"""

    def test_error_result_format(self):
        # Given: Error message
        message = 'Seat already reserved'
        # When: Create error result
        result = SeatStateCommandHandlerImpl._error_result(message)
        # Then: Should return standardized error format
        assert result['success'] is False
        assert result['error_message'] == 'Seat already reserved'
        assert result['reserved_seats'] == []

    def test_error_result_with_complex_message(self):
        # Given: Complex error message
        message = 'Seat A-1-1-1 is already SOLD'
        # When: Create error result
        result = SeatStateCommandHandlerImpl._error_result(message)
        # Then: Should preserve exact message
        assert result['success'] is False
        assert result['error_message'] == 'Seat A-1-1-1 is already SOLD'
        assert result['reserved_seats'] == []


# ============================================================================
# Test Business Logic - _parse_seat_positions
# ============================================================================


@pytest.mark.unit
class TestParseSeatPositions:
    """Test seat position parsing logic"""

    def test_parse_single_seat(self):
        # Given: Handler instance and single seat ID
        handler = SeatStateCommandHandlerImpl(booking_metadata_handler=Mock())
        seat_ids = ['1-1']

        # When: Parse seat positions
        result = handler._parse_seat_positions(
            seat_ids=seat_ids, section='A', subsection=1, seats_per_row=10
        )

        # Then: Should return correct tuple format
        assert len(result) == 1
        row, seat_num, seat_index, seat_id = result[0]
        assert row == 1
        assert seat_num == 1
        assert seat_index == 0
        assert seat_id == 'A-1-1-1'

    def test_parse_multiple_seats(self):
        # Given: Handler instance and multiple seat IDs
        handler = SeatStateCommandHandlerImpl(booking_metadata_handler=Mock())
        seat_ids = ['1-1', '1-2', '2-1']

        # When: Parse seat positions
        result = handler._parse_seat_positions(
            seat_ids=seat_ids, section='B', subsection=2, seats_per_row=5
        )

        # Then: Should return correct tuples for all seats
        assert len(result) == 3
        assert result[0] == (1, 1, 0, 'B-2-1-1')
        assert result[1] == (1, 2, 1, 'B-2-1-2')
        assert result[2] == (2, 1, 5, 'B-2-2-1')

    def test_parse_with_different_sections(self):
        # Given: Handler instance
        handler = SeatStateCommandHandlerImpl(booking_metadata_handler=Mock())
        seat_ids = ['3-7']

        # When: Parse seat positions with section C, subsection 3
        result = handler._parse_seat_positions(
            seat_ids=seat_ids, section='C', subsection=3, seats_per_row=8
        )

        # Then: Should include section and subsection in seat_id
        row, seat_num, seat_index, seat_id = result[0]
        assert row == 3
        assert seat_num == 7
        assert seat_index == 22
        assert seat_id == 'C-3-3-7'

    def test_parse_consecutive_seats_same_row(self):
        # Given: Handler instance and 4 consecutive seats
        handler = SeatStateCommandHandlerImpl(booking_metadata_handler=Mock())
        seat_ids = ['1-1', '1-2', '1-3', '1-4']

        # When: Parse seat positions
        result = handler._parse_seat_positions(
            seat_ids=seat_ids, section='A', subsection=1, seats_per_row=10
        )

        # Then: Should return consecutive indices (0, 1, 2, 3)
        assert len(result) == 4
        assert result == [
            (1, 1, 0, 'A-1-1-1'),  # row, seat_num, index, seat_id
            (1, 2, 1, 'A-1-1-2'),
            (1, 3, 2, 'A-1-1-3'),
            (1, 4, 3, 'A-1-1-4'),
        ]
