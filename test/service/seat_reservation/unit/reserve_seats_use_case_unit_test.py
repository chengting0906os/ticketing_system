"""
Unit tests for ReserveSeatsUseCase

Test Coverage:
1. Request validation (manual mode, best_available mode, invalid mode)
2. Successful reservation flow (manual + best_available)
3. Error handling (reservation failure, domain error, unexpected error)
4. Event publishing (success + failure scenarios)
"""

from unittest.mock import AsyncMock

import pytest

from src.platform.exception.exceptions import DomainError
from src.service.seat_reservation.app.command.reserve_seats_use_case import (
    ReservationRequest,
    ReserveSeatsUseCase,
)


# Mark this file as unit tests to prevent pytest-bdd from collecting it
pytestmark = pytest.mark.unit


class TestReservationRequestValidation:
    """Test request validation logic"""

    def setup_method(self):
        """Setup test fixtures"""
        # Create mocked dependencies
        self.seat_state_handler = AsyncMock()
        self.mq_publisher = AsyncMock()
        self.event_state_broadcaster = AsyncMock()

        # Create use case instance
        self.use_case = ReserveSeatsUseCase(
            seat_state_handler=self.seat_state_handler,
            mq_publisher=self.mq_publisher,
            event_state_broadcaster=self.event_state_broadcaster,
        )

    # ==================== Manual Mode Validation ====================

    @pytest.mark.asyncio
    async def test_manual_mode_requires_seat_positions(self):
        """Manual mode should require seat_positions"""
        # Given: Manual mode request without seat positions
        request = ReservationRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            event_id=123,
            selection_mode='manual',
            section_filter='A',
            subsection_filter=1,
            quantity=0,
            seat_positions=None,  # Missing!
        )

        # When: Reserve seats
        result = await self.use_case.reserve_seats(request)

        # Then: Should fail with error
        assert result.success is False
        assert result.error_message is not None
        assert 'Manual selection requires seat positions' in result.error_message

        # And: Should publish failure event
        self.mq_publisher.publish_reservation_failed.assert_called_once()

    @pytest.mark.asyncio
    async def test_manual_mode_requires_seat_positions_empty_list(self):
        """Manual mode should reject empty seat positions list"""
        # Given: Manual mode request with empty seat positions
        request = ReservationRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            event_id=123,
            selection_mode='manual',
            section_filter='A',
            subsection_filter=1,
            quantity=0,
            seat_positions=[],  # Empty!
        )

        # When: Reserve seats
        result = await self.use_case.reserve_seats(request)

        # Then: Should fail with error
        assert result.success is False
        assert result.error_message is not None
        assert 'Manual selection requires seat positions' in result.error_message

    @pytest.mark.asyncio
    async def test_manual_mode_cannot_reserve_more_than_4_seats(self):
        """Manual mode should reject more than 4 seats"""
        # Given: Manual mode request with 5 seats
        request = ReservationRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            event_id=123,
            selection_mode='manual',
            section_filter='A',
            subsection_filter=1,
            quantity=0,
            seat_positions=['1-1', '1-2', '1-3', '1-4', '1-5'],  # 5 seats!
        )

        # When: Reserve seats
        result = await self.use_case.reserve_seats(request)

        # Then: Should fail with error
        assert result.success is False
        assert result.error_message is not None
        assert 'Cannot reserve more than 4 seats at once' in result.error_message

    # ==================== Best Available Mode Validation ====================

    @pytest.mark.asyncio
    async def test_best_available_mode_requires_quantity(self):
        """Best available mode should require quantity"""
        # Given: Best available mode request without quantity (using 0 or negative)
        request = ReservationRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            event_id=123,
            selection_mode='best_available',
            section_filter='A',
            subsection_filter=1,
            quantity=0,  # Invalid! (Using 0 to simulate "not provided")
        )

        # When: Reserve seats
        result = await self.use_case.reserve_seats(request)

        # Then: Should fail with error
        assert result.success is False
        assert result.error_message is not None
        assert 'Best available selection requires valid quantity' in result.error_message

    @pytest.mark.asyncio
    async def test_best_available_mode_requires_positive_quantity(self):
        """Best available mode should require quantity > 0"""
        # Given: Best available mode request with quantity = 0
        request = ReservationRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            event_id=123,
            selection_mode='best_available',
            quantity=0,  # Invalid!
            section_filter='A',
            subsection_filter=1,
        )

        # When: Reserve seats
        result = await self.use_case.reserve_seats(request)

        # Then: Should fail with error
        assert result.success is False
        assert result.error_message is not None
        assert 'Best available selection requires valid quantity' in result.error_message

    @pytest.mark.asyncio
    async def test_best_available_mode_cannot_reserve_more_than_4_seats(self):
        """Best available mode should reject quantity > 4"""
        # Given: Best available mode request with quantity = 5
        request = ReservationRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            event_id=123,
            selection_mode='best_available',
            quantity=5,  # Too many!
            section_filter='A',
            subsection_filter=1,
        )

        # When: Reserve seats
        result = await self.use_case.reserve_seats(request)

        # Then: Should fail with error
        assert result.success is False
        assert result.error_message is not None
        assert 'Cannot reserve more than 4 seats at once' in result.error_message

    @pytest.mark.asyncio
    async def test_best_available_mode_requires_section_filter(self):
        """Best available mode should require section filter"""
        # Given: Best available mode request with empty section filter
        request = ReservationRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            event_id=123,
            selection_mode='best_available',
            section_filter='',  # Empty string!
            subsection_filter=1,
            quantity=2,
        )

        # When: Reserve seats
        result = await self.use_case.reserve_seats(request)

        # Then: Should fail with error
        assert result.success is False
        assert result.error_message is not None
        assert 'Best available mode requires section and subsection filter' in result.error_message

    @pytest.mark.asyncio
    async def test_best_available_mode_requires_subsection_filter(self):
        """Best available mode should require subsection filter"""
        # Given: Best available mode request with negative subsection filter
        request = ReservationRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            event_id=123,
            selection_mode='best_available',
            section_filter='A',
            subsection_filter=-1,  # Invalid subsection!
            quantity=2,
        )

        # When: Reserve seats
        result = await self.use_case.reserve_seats(request)

        # Then: Should fail with error
        assert result.success is False
        assert result.error_message is not None
        assert 'Best available mode requires section and subsection filter' in result.error_message

    # ==================== Invalid Mode ====================

    @pytest.mark.asyncio
    async def test_invalid_selection_mode(self):
        """Should reject invalid selection mode"""
        # Given: Request with invalid selection mode
        request = ReservationRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            event_id=123,
            selection_mode='invalid_mode',  # Invalid!
            section_filter='A',
            subsection_filter=1,
            quantity=2,
        )

        # When: Reserve seats
        result = await self.use_case.reserve_seats(request)

        # Then: Should fail with error
        assert result.success is False
        assert result.error_message is not None
        assert 'Invalid selection mode: invalid_mode' in result.error_message


class TestReserveSeatsSuccessFlow:
    """Test successful reservation flow"""

    def setup_method(self):
        """Setup test fixtures"""
        # Create mocked dependencies
        self.seat_state_handler = AsyncMock()
        self.mq_publisher = AsyncMock()
        self.event_state_broadcaster = AsyncMock()

        # Create use case instance
        self.use_case = ReserveSeatsUseCase(
            seat_state_handler=self.seat_state_handler,
            mq_publisher=self.mq_publisher,
            event_state_broadcaster=self.event_state_broadcaster,
        )

    @pytest.mark.asyncio
    async def test_successful_manual_reservation(self):
        """Should successfully reserve seats in manual mode"""
        # Given: Valid manual reservation request
        request = ReservationRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            event_id=123,
            selection_mode='manual',
            section_filter='A',
            subsection_filter=1,
            quantity=2,
            seat_positions=['1-1', '1-2'],
        )

        # And: Seat state handler returns success
        self.seat_state_handler.reserve_seats_atomic.return_value = {
            'success': True,
            'reserved_seats': ['A-1-1-1', 'A-1-1-2'],
            'total_price': 2000,
            'subsection_stats': {'available': 98, 'reserved': 2},
            'event_stats': {'available': 498, 'reserved': 2},
            'event_state': {'sections': {}},
        }

        # When: Reserve seats
        result = await self.use_case.reserve_seats(request)

        # Then: Should succeed
        assert result.success is True
        assert result.booking_id == 'test-booking-id'
        assert result.reserved_seats == ['A-1-1-1', 'A-1-1-2']
        assert result.total_price == 2000
        assert result.event_id == 123

        # And: Should call seat state handler with correct params
        self.seat_state_handler.reserve_seats_atomic.assert_called_once_with(
            event_id=123,
            booking_id='test-booking-id',
            buyer_id=1,
            mode='manual',
            section='A',
            subsection=1,
            quantity=2,
            seat_ids=['1-1', '1-2'],
        )

        # And: Should broadcast event state
        self.event_state_broadcaster.broadcast_event_state.assert_called_once_with(
            event_id=123, event_state={'sections': {}}
        )

        # And: Should publish success event
        self.mq_publisher.publish_seats_reserved.assert_called_once_with(
            booking_id='test-booking-id',
            buyer_id=1,
            event_id=123,
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['A-1-1-1', 'A-1-1-2'],
            total_price=2000,
            subsection_stats={'available': 98, 'reserved': 2},
            event_stats={'available': 498, 'reserved': 2},
        )

    @pytest.mark.asyncio
    async def test_successful_best_available_reservation(self):
        """Should successfully reserve seats in best_available mode"""
        # Given: Valid best_available reservation request
        request = ReservationRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            event_id=123,
            selection_mode='best_available',
            quantity=3,
            section_filter='B',
            subsection_filter=2,
        )

        # And: Seat state handler returns success
        self.seat_state_handler.reserve_seats_atomic.return_value = {
            'success': True,
            'reserved_seats': ['B-2-1-1', 'B-2-1-2', 'B-2-1-3'],
            'total_price': 3000,
            'subsection_stats': {'available': 97, 'reserved': 3},
            'event_stats': {'available': 497, 'reserved': 3},
            'event_state': {'sections': {}},
        }

        # When: Reserve seats
        result = await self.use_case.reserve_seats(request)

        # Then: Should succeed
        assert result.success is True
        assert result.booking_id == 'test-booking-id'
        assert result.reserved_seats == ['B-2-1-1', 'B-2-1-2', 'B-2-1-3']
        assert result.total_price == 3000

        # And: Should call seat state handler with correct params
        self.seat_state_handler.reserve_seats_atomic.assert_called_once_with(
            event_id=123,
            booking_id='test-booking-id',
            buyer_id=1,
            mode='best_available',
            section='B',
            subsection=2,
            quantity=3,
            seat_ids=None,
        )

    @pytest.mark.asyncio
    async def test_should_handle_subsection_sold_out(self):
        """Should handle subsection sold out scenario"""
        # Given: Request that will sell out subsection
        request = ReservationRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            event_id=123,
            selection_mode='manual',
            section_filter='A',
            subsection_filter=1,
            quantity=1,
            seat_positions=['1-1'],
        )

        # And: Seat state handler returns subsection sold out
        self.seat_state_handler.reserve_seats_atomic.return_value = {
            'success': True,
            'reserved_seats': ['A-1-1-1'],
            'total_price': 1000,
            'subsection_stats': {'available': 0, 'reserved': 100},  # Sold out!
            'event_stats': {'available': 400, 'reserved': 100},
            'event_state': {'sections': {}},
        }

        # When: Reserve seats
        result = await self.use_case.reserve_seats(request)

        # Then: Should successfully reserve seats even when subsection sold out
        assert result.success is True
        assert result.reserved_seats == ['A-1-1-1']


class TestReserveSeatsErrorHandling:
    """Test error handling scenarios"""

    def setup_method(self):
        """Setup test fixtures"""
        # Create mocked dependencies
        self.seat_state_handler = AsyncMock()
        self.mq_publisher = AsyncMock()
        self.event_state_broadcaster = AsyncMock()

        # Create use case instance
        self.use_case = ReserveSeatsUseCase(
            seat_state_handler=self.seat_state_handler,
            mq_publisher=self.mq_publisher,
            event_state_broadcaster=self.event_state_broadcaster,
        )

    @pytest.mark.asyncio
    async def test_handle_reservation_failure_from_handler(self):
        """Should handle reservation failure from seat state handler"""
        # Given: Valid request
        request = ReservationRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            event_id=123,
            selection_mode='manual',
            section_filter='A',
            subsection_filter=1,
            quantity=1,
            seat_positions=['1-1'],
        )

        # And: Seat state handler returns failure
        self.seat_state_handler.reserve_seats_atomic.return_value = {
            'success': False,
            'error_message': 'Seats already reserved',
        }

        # When: Reserve seats
        result = await self.use_case.reserve_seats(request)

        # Then: Should return failure result
        assert result.success is False
        assert result.booking_id == 'test-booking-id'
        assert result.error_message == 'Seats already reserved'

        # And: Should publish failure event
        self.mq_publisher.publish_reservation_failed.assert_called_once()
        call_kwargs = self.mq_publisher.publish_reservation_failed.call_args.kwargs
        assert call_kwargs['booking_id'] == 'test-booking-id'
        assert call_kwargs['error_message'] == 'Seats already reserved'

    @pytest.mark.asyncio
    async def test_handle_domain_error(self):
        """Should handle DomainError from seat state handler"""
        # Given: Valid request
        request = ReservationRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            event_id=123,
            selection_mode='manual',
            section_filter='A',
            subsection_filter=1,
            quantity=1,
            seat_positions=['1-1'],
        )

        # And: Seat state handler raises DomainError
        self.seat_state_handler.reserve_seats_atomic.side_effect = DomainError(
            'Insufficient seats available', 400
        )

        # When: Reserve seats
        result = await self.use_case.reserve_seats(request)

        # Then: Should return failure result
        assert result.success is False
        assert result.error_message == 'Insufficient seats available'

        # And: Should publish failure event
        self.mq_publisher.publish_reservation_failed.assert_called_once()
        call_kwargs = self.mq_publisher.publish_reservation_failed.call_args.kwargs
        assert call_kwargs['error_message'] == 'Insufficient seats available'

    @pytest.mark.asyncio
    async def test_handle_unexpected_exception(self):
        """Should handle unexpected exceptions gracefully"""
        # Given: Valid request
        request = ReservationRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            event_id=123,
            selection_mode='manual',
            section_filter='A',
            subsection_filter=1,
            quantity=1,
            seat_positions=['1-1'],
        )

        # And: Seat state handler raises unexpected exception
        self.seat_state_handler.reserve_seats_atomic.side_effect = RuntimeError(
            'Database connection lost'
        )

        # When: Reserve seats
        result = await self.use_case.reserve_seats(request)

        # Then: Should return generic error message (don't leak internal details)
        assert result.success is False
        assert result.error_message == 'Internal server error'

        # And: Should publish failure event
        self.mq_publisher.publish_reservation_failed.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_not_broadcast_on_failure(self):
        """Should not broadcast event state when reservation fails"""
        # Given: Valid request
        request = ReservationRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            event_id=123,
            selection_mode='manual',
            section_filter='A',
            subsection_filter=1,
            quantity=1,
            seat_positions=['1-1'],
        )

        # And: Seat state handler returns failure
        self.seat_state_handler.reserve_seats_atomic.return_value = {
            'success': False,
            'error_message': 'Seats already reserved',
        }

        # When: Reserve seats
        await self.use_case.reserve_seats(request)

        # Then: Should NOT broadcast event state
        self.event_state_broadcaster.broadcast_event_state.assert_not_called()

        # And: Should NOT publish success event
        self.mq_publisher.publish_seats_reserved.assert_not_called()
