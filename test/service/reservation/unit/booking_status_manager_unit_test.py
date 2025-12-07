"""
Unit tests for BookingStatusManager

Tests idempotency control and booking status management logic.
"""

from typing import Any

import pytest
from src.service.reservation.driven_adapter.reservation_helper.booking_status_manager import (
    BookingStatusManager,
)
import uuid_utils as uuid
from uuid_utils import UUID

from src.service.shared_kernel.app.interface.i_booking_metadata_handler import (
    IBookingMetadataHandler,
)


class MockBookingMetadataHandler(IBookingMetadataHandler):
    """Mock implementation of IBookingMetadataHandler for testing"""

    def __init__(self) -> None:
        self.metadata: dict[str, dict[str, Any]] = {}

    async def get_booking_metadata(self, *, booking_id: str) -> dict[str, Any] | None:
        """Get booking metadata"""
        return self.metadata.get(booking_id)

    async def update_booking_status(
        self, *, booking_id: str, status: str, error_message: str = ''
    ) -> None:
        """Update booking status"""
        if booking_id not in self.metadata:
            self.metadata[booking_id] = {}

        self.metadata[booking_id]['status'] = status
        if error_message:
            self.metadata[booking_id]['error_message'] = error_message

    async def save_booking_metadata(
        self,
        *,
        booking_id: str,
        buyer_id: int,
        event_id: int,
        section: str,
        subsection: int,
        quantity: int,
        seat_selection_mode: str,
        seat_positions: list[str],
    ) -> bool:
        """Save booking metadata. Returns True if newly created, False if already exists."""
        if booking_id in self.metadata:
            return False  # Already exists (idempotency)
        self.metadata[booking_id] = {
            'booking_id': booking_id,
            'buyer_id': str(buyer_id),
            'event_id': str(event_id),
            'section': section,
            'subsection': str(subsection),
            'quantity': str(quantity),
            'seat_selection_mode': seat_selection_mode,
            'seat_positions': str(seat_positions),
            'status': 'PENDING_RESERVATION',
        }
        return True

    async def delete_booking_metadata(self, *, booking_id: str) -> None:
        """Delete booking metadata"""
        if booking_id in self.metadata:
            del self.metadata[booking_id]


class TestBookingStatusManager:
    @pytest.fixture
    def booking_id(self) -> UUID:
        """Generate a UUID7 booking ID for testing"""
        return uuid.uuid7()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_booking_status_no_metadata(self, booking_id: UUID) -> None:
        """Test checking status when no metadata exists"""
        # Given: Empty metadata handler
        mock_handler = MockBookingMetadataHandler()
        manager = BookingStatusManager(booking_metadata_handler=mock_handler)

        # When: Check status for non-existent booking
        result = await manager.check_booking_status(booking_id=str(booking_id))

        # Then: Should return None to proceed with reservation
        assert result is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_booking_status_pending_reservation(self, booking_id: UUID) -> None:
        """Test checking status when booking is in PENDING_RESERVATION state"""
        # Given: Booking with PENDING_RESERVATION status
        mock_handler = MockBookingMetadataHandler()
        mock_handler.metadata[str(booking_id)] = {'status': 'PENDING_RESERVATION'}
        manager = BookingStatusManager(booking_metadata_handler=mock_handler)

        # When: Check status
        result = await manager.check_booking_status(booking_id=str(booking_id))

        # Then: Should return None to proceed with reservation
        assert result is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_booking_status_reserve_success(self, booking_id: UUID) -> None:
        """Test checking status when booking already succeeded"""
        # Given: Booking with RESERVE_SUCCESS status and complete data
        mock_handler = MockBookingMetadataHandler()
        mock_handler.metadata[str(booking_id)] = {
            'status': 'RESERVE_SUCCESS',
            'reserved_seats': '["A-1-1-1", "A-1-1-2"]',
            'total_price': 2000,
            'subsection_stats': '{"section_id": "A-1", "available": 8}',
            'event_stats': '{"event_id": 1, "available": 98}',
        }
        manager = BookingStatusManager(booking_metadata_handler=mock_handler)

        # When: Check status
        result = await manager.check_booking_status(booking_id=str(booking_id))

        # Then: Should return cached result
        assert result is not None
        assert result['success'] is True
        assert result['reserved_seats'] == ['A-1-1-1', 'A-1-1-2']
        assert result['total_price'] == 2000
        assert result['subsection_stats'] == {'section_id': 'A-1', 'available': 8}
        assert result['event_stats'] == {'event_id': 1, 'available': 98}
        assert result['error_message'] is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_booking_status_reserve_failed(self, booking_id: UUID) -> None:
        """Test checking status when booking already failed"""
        # Given: Booking with RESERVE_FAILED status
        mock_handler = MockBookingMetadataHandler()
        mock_handler.metadata[str(booking_id)] = {
            'status': 'RESERVE_FAILED',
            'error_message': 'Seat A-1-1-1 is already RESERVED',
        }
        manager = BookingStatusManager(booking_metadata_handler=mock_handler)

        # When: Check status
        result = await manager.check_booking_status(booking_id=str(booking_id))

        # Then: Should return error result
        assert result is not None
        assert result['success'] is False
        assert result['error_message'] == 'Seat A-1-1-1 is already RESERVED'
        assert result['reserved_seats'] is None
        assert result['total_price'] == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_booking_status_unknown_status(self, booking_id: UUID) -> None:
        """Test checking status with unknown status value"""
        # Given: Booking with unknown status
        mock_handler = MockBookingMetadataHandler()
        mock_handler.metadata[str(booking_id)] = {'status': 'UNKNOWN_STATUS'}
        manager = BookingStatusManager(booking_metadata_handler=mock_handler)

        # When: Check status
        result = await manager.check_booking_status(booking_id=str(booking_id))

        # Then: Should return None to proceed (defensive approach)
        assert result is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_save_reservation_failure(self, booking_id: UUID) -> None:
        """Test saving reservation failure"""
        # Given: Empty metadata handler
        mock_handler = MockBookingMetadataHandler()
        manager = BookingStatusManager(booking_metadata_handler=mock_handler)

        # When: Save failure
        await manager.save_reservation_failure(
            booking_id=str(booking_id), error_message='Seats not available'
        )

        # Then: Status and error should be saved
        assert mock_handler.metadata[str(booking_id)]['status'] == 'RESERVE_FAILED'
        assert mock_handler.metadata[str(booking_id)]['error_message'] == 'Seats not available'

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_booking_status_reserve_success_missing_data(
        self, booking_id: UUID
    ) -> None:
        """Test RESERVE_SUCCESS with missing data fields"""
        # Given: RESERVE_SUCCESS with minimal data
        mock_handler = MockBookingMetadataHandler()
        mock_handler.metadata[str(booking_id)] = {
            'status': 'RESERVE_SUCCESS',
            # Missing most fields
        }
        manager = BookingStatusManager(booking_metadata_handler=mock_handler)

        # When: Check status
        result = await manager.check_booking_status(booking_id=str(booking_id))

        # Then: Should still return result with defaults
        assert result is not None
        assert result['success'] is True
        assert result['reserved_seats'] == []  # Default empty array
        assert result['total_price'] == 0  # Default 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_idempotency_prevents_duplicate_reservation(self, booking_id: UUID) -> None:
        """Test that idempotency check prevents duplicate reservations"""
        # Given: Manager with successful reservation
        mock_handler = MockBookingMetadataHandler()
        mock_handler.metadata[str(booking_id)] = {
            'status': 'RESERVE_SUCCESS',
            'reserved_seats': '["A-1-1-1"]',
            'total_price': 1000,
            'subsection_stats': '{}',
            'event_stats': '{}',
        }
        manager = BookingStatusManager(booking_metadata_handler=mock_handler)

        # When: Check status twice
        result1 = await manager.check_booking_status(booking_id=str(booking_id))
        result2 = await manager.check_booking_status(booking_id=str(booking_id))

        # Then: Both should return the same cached result
        assert result1 == result2
        assert result1 is not None  # Add type guard for mypy/pyrefly
        assert result1['success'] is True
        assert result1['reserved_seats'] == ['A-1-1-1']
