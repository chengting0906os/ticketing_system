"""
Unit tests for CreateBookingUseCase

Tests the simplified booking creation flow:
1. UUID7 generation
2. Seat availability validation (Fail Fast)
3. Publish to Booking Service (Kafka)
4. Return booking immediately

Note: Downstream services (Booking, Reservation) handle metadata + PostgreSQL.
"""

from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from uuid_utils import UUID

from src.platform.exception.exceptions import DomainError
from src.service.ticketing.app.command.create_booking_use_case import CreateBookingUseCase
from src.service.ticketing.app.interface.i_seat_availability_query_handler import (
    ISeatAvailabilityQueryHandler,
)


@pytest.fixture
def mock_event_publisher() -> Mock:
    """Mock event publisher"""
    publisher = AsyncMock()
    publisher.publish_booking_created = AsyncMock()
    return publisher


class StubSeatAvailabilityHandler(ISeatAvailabilityQueryHandler):
    """Stub that provides configurable seat availability responses"""

    def __init__(self, is_available: bool = True) -> None:
        self._is_available = is_available

    async def check_availability(
        self, *, event_id: int, section: str, subsection: int, required_quantity: int
    ) -> bool:
        """Always returns the configured availability (ignores actual parameters)"""
        _ = event_id, section, subsection, required_quantity  # Unused in stub
        return self._is_available


@pytest.fixture
def stub_seat_availability_handler() -> StubSeatAvailabilityHandler:
    """Factory that creates stub with default availability = True"""
    return StubSeatAvailabilityHandler(is_available=True)


@pytest.fixture
def create_booking_use_case(
    mock_event_publisher: Mock,
    stub_seat_availability_handler: StubSeatAvailabilityHandler,
) -> CreateBookingUseCase:
    """Create instance of CreateBookingUseCase with mocked dependencies"""
    return CreateBookingUseCase(
        event_publisher=mock_event_publisher,
        seat_availability_handler=stub_seat_availability_handler,
    )


@pytest.fixture
def valid_booking_params() -> dict[str, Any]:
    """Valid booking parameters"""
    return {
        'buyer_id': 123,
        'event_id': 1,
        'section': 'A',
        'subsection': 1,
        'seat_selection_mode': 'best_available',
        'seat_positions': [],
        'quantity': 2,
    }


@pytest.mark.unit
class TestCreateBookingUseCase:
    """Test CreateBookingUseCase"""

    @pytest.mark.asyncio
    async def test_create_booking_success__generates_uuid7(
        self,
        create_booking_use_case: CreateBookingUseCase,
        mock_event_publisher: Mock,
        valid_booking_params: dict[str, Any],
    ) -> None:
        """Test successful booking creation generates UUID7"""
        # Arrange - stub defaults to returning True (seats available)

        # Act
        with patch(
            'src.service.ticketing.app.command.create_booking_use_case.uuid_utils.uuid7'
        ) as mock_uuid7:
            test_uuid = UUID('01936d8f-5e73-7c4e-a9c5-123456789abc')  # Valid UUID7
            mock_uuid7.return_value = test_uuid

            result = await create_booking_use_case.create_booking(**valid_booking_params)

        # Assert - UUID7 was generated
        mock_uuid7.assert_called_once()

        # Assert - Event published to Booking Service
        mock_event_publisher.publish_booking_created.assert_awaited_once()

        # Assert - Returned booking has correct UUID7
        assert result.id == test_uuid

    @pytest.mark.asyncio
    async def test_create_booking_fail__insufficient_seats(
        self,
        mock_event_publisher: Mock,
        valid_booking_params: dict[str, Any],
    ) -> None:
        """Test booking creation fails when insufficient seats available"""
        # Arrange - Create stub that returns False (seats unavailable)
        stub_seat_availability_handler = StubSeatAvailabilityHandler(is_available=False)
        use_case = CreateBookingUseCase(
            event_publisher=mock_event_publisher,
            seat_availability_handler=stub_seat_availability_handler,
        )

        # Act & Assert
        with pytest.raises(DomainError) as exc_info:
            await use_case.create_booking(**valid_booking_params)

        assert 'Insufficient seats available' in str(exc_info.value)
        assert exc_info.value.status_code == 400

        # Assert - No event published (fail fast)
        mock_event_publisher.publish_booking_created.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_booking_success__event_published(
        self,
        create_booking_use_case: CreateBookingUseCase,
        mock_event_publisher: Mock,
        valid_booking_params: dict[str, Any],
    ) -> None:
        """Test that BookingCreated event is published to Booking Service"""
        # Act
        await create_booking_use_case.create_booking(**valid_booking_params)

        # Assert - Event published
        mock_event_publisher.publish_booking_created.assert_awaited_once()

        # Verify the event object passed has correct type
        call_args = mock_event_publisher.publish_booking_created.call_args
        assert call_args is not None
        assert 'event' in call_args.kwargs

    @pytest.mark.asyncio
    async def test_create_booking__manual_mode_with_seat_positions(
        self,
        create_booking_use_case: CreateBookingUseCase,
        mock_event_publisher: Mock,
        valid_booking_params: dict[str, Any],
    ) -> None:
        """Test booking creation with manual seat selection mode"""
        # Arrange
        valid_booking_params['seat_selection_mode'] = 'manual'
        valid_booking_params['seat_positions'] = ['1-1', '1-2']

        # Act
        result = await create_booking_use_case.create_booking(**valid_booking_params)

        # Assert - Event published with seat positions
        mock_event_publisher.publish_booking_created.assert_awaited_once()
        call_args = mock_event_publisher.publish_booking_created.call_args
        event = call_args.kwargs['event']
        assert event.seat_selection_mode == 'manual'
        assert event.seat_positions == ['1-1', '1-2']

        # Assert - Booking entity has correct values
        assert result.seat_selection_mode == 'manual'
        assert result.seat_positions == ['1-1', '1-2']

    @pytest.mark.asyncio
    async def test_create_booking__sets_custom_uuid_on_booking_entity(
        self,
        create_booking_use_case: CreateBookingUseCase,
        valid_booking_params: dict[str, Any],
    ) -> None:
        """Test that booking entity receives custom UUID7 id"""
        # Act
        with patch(
            'src.service.ticketing.app.command.create_booking_use_case.uuid_utils.uuid7'
        ) as mock_uuid7:
            test_uuid = UUID('01936d8f-5e73-7c4e-a9c5-123456789abc')
            mock_uuid7.return_value = test_uuid

            result = await create_booking_use_case.create_booking(**valid_booking_params)

        # Assert - Booking entity has UUID7 as id
        assert result is not None
        assert result.id == test_uuid  # UUID object, not string
