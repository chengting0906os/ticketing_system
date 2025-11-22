import pytest

from src.service.seat_reservation.driven_adapter.seat_reservation_helper.atomic_reservation_executor import (
    AtomicReservationExecutor,
)


# ============================================================================
# Test _extract_subsection_stats
# ============================================================================


@pytest.mark.unit
class TestExtractSubsectionStats:
    """Test subsection statistics extraction"""

    def test_extract_valid_stats(self):
        # Given: Valid event state with subsection stats
        event_state = {
            'sections': {
                'A': {
                    'subsections': {
                        '1': {'stats': {'available': 98, 'reserved': 2, 'sold': 0, 'total': 100}}
                    }
                }
            }
        }

        # When: Extract subsection stats
        result = AtomicReservationExecutor._extract_subsection_stats(event_state, 'A-1')

        # Then: Should return correct stats
        assert result == {'available': 98, 'reserved': 2, 'sold': 0, 'total': 100}

    def test_extract_different_section(self):
        # Given: Event state with multiple sections
        event_state = {
            'sections': {
                'B': {
                    'subsections': {
                        '2': {'stats': {'available': 50, 'reserved': 10, 'sold': 40, 'total': 100}}
                    }
                }
            }
        }

        # When: Extract section B-2 stats
        result = AtomicReservationExecutor._extract_subsection_stats(event_state, 'B-2')

        # Then: Should return B-2 stats
        assert result == {'available': 50, 'reserved': 10, 'sold': 40, 'total': 100}


# ============================================================================
# Test _extract_event_stats
# ============================================================================


@pytest.mark.unit
class TestExtractEventStats:
    """Test event-level statistics extraction"""

    def test_extract_valid_event_stats(self):
        # Given: Valid event state with event stats
        event_state = {'event_stats': {'available': 498, 'reserved': 2, 'sold': 0, 'total': 500}}

        # When: Extract event stats
        result = AtomicReservationExecutor._extract_event_stats(event_state)

        # Then: Should return correct stats
        assert result == {'available': 498, 'reserved': 2, 'sold': 0, 'total': 500}

    def test_extract_with_sold_seats(self):
        # Given: Event state with some seats sold
        event_state = {'event_stats': {'available': 400, 'reserved': 50, 'sold': 50, 'total': 500}}

        # When: Extract event stats
        result = AtomicReservationExecutor._extract_event_stats(event_state)

        # Then: Should return correct stats including sold
        assert result == {'available': 400, 'reserved': 50, 'sold': 50, 'total': 500}
