"""
Unit tests for CreateBookingUseCase

Tests the optimized booking creation flow:
1. UUID7 generation
2. Kvrocks metadata storage
3. PostgreSQL persistence
4. Kafka event publishing
"""

from unittest.mock import AsyncMock, patch

import pytest
from uuid_utils import UUID

from src.platform.exception.exceptions import DomainError
from src.service.ticketing.app.command.create_booking_use_case import CreateBookingUseCase


@pytest.fixture
def mock_booking_metadata_handler():
    """Mock booking metadata handler"""
    handler = AsyncMock()
    handler.save_booking_metadata = AsyncMock()
    handler.delete_booking_metadata = AsyncMock()
    return handler


@pytest.fixture
def mock_booking_command_repo():
    """Mock booking command repository"""
    repo = AsyncMock()
    repo.create = AsyncMock()
    return repo


@pytest.fixture
def mock_event_publisher():
    """Mock event publisher"""
    publisher = AsyncMock()
    publisher.publish_booking_created = AsyncMock()
    return publisher


@pytest.fixture
def mock_seat_availability_handler():
    """Mock seat availability query handler"""
    handler = AsyncMock()
    handler.check_subsection_availability = AsyncMock()
    return handler


@pytest.fixture
def create_booking_use_case(
    mock_booking_metadata_handler,
    mock_booking_command_repo,
    mock_event_publisher,
    mock_seat_availability_handler,
):
    """Create instance of CreateBookingUseCase with mocked dependencies"""
    return CreateBookingUseCase(
        booking_metadata_handler=mock_booking_metadata_handler,
        booking_command_repo=mock_booking_command_repo,
        event_publisher=mock_event_publisher,
        seat_availability_handler=mock_seat_availability_handler,
    )


@pytest.fixture
def valid_booking_params():
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
        create_booking_use_case,
        mock_seat_availability_handler,
        mock_booking_metadata_handler,
        mock_booking_command_repo,
        mock_event_publisher,
        valid_booking_params,
    ):
        """Test successful booking creation generates UUID7"""
        # Arrange
        mock_seat_availability_handler.check_subsection_availability.return_value = True

        # Act
        with patch(
            'src.service.ticketing.app.command.create_booking_use_case.uuid_utils.uuid7'
        ) as mock_uuid7:
            test_uuid = UUID('01936d8f-5e73-7c4e-a9c5-123456789abc')  # Valid UUID7
            mock_uuid7.return_value = test_uuid

            result = await create_booking_use_case.create_booking(**valid_booking_params)

        # Assert - UUID7 was generated
        mock_uuid7.assert_called_once()

        # Assert - Booking metadata saved to Kvrocks with UUID7
        mock_booking_metadata_handler.save_booking_metadata.assert_awaited_once()
        call_kwargs = mock_booking_metadata_handler.save_booking_metadata.call_args.kwargs
        assert call_kwargs['booking_id'] == str(test_uuid)
        assert call_kwargs['buyer_id'] == valid_booking_params['buyer_id']
        assert call_kwargs['event_id'] == valid_booking_params['event_id']
        assert call_kwargs['section'] == valid_booking_params['section']
        assert call_kwargs['subsection'] == valid_booking_params['subsection']

        # Assert - PostgreSQL NOT called (deferred to event consumer)
        mock_booking_command_repo.create.assert_not_awaited()

        # Assert - Returned booking has correct UUID7
        assert result.id == test_uuid

    @pytest.mark.asyncio
    async def test_create_booking_fail__insufficient_seats(
        self,
        create_booking_use_case,
        mock_seat_availability_handler,
        mock_booking_metadata_handler,
        valid_booking_params,
    ):
        """Test booking creation fails when insufficient seats available"""
        # Arrange
        mock_seat_availability_handler.check_subsection_availability.return_value = False

        # Act & Assert
        with pytest.raises(DomainError) as exc_info:
            await create_booking_use_case.create_booking(**valid_booking_params)

        assert 'Insufficient seats available' in str(exc_info.value)
        assert exc_info.value.status_code == 400

        # Assert - No metadata saved (fail fast)
        mock_booking_metadata_handler.save_booking_metadata.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_booking_success__event_published(
        self,
        create_booking_use_case,
        mock_seat_availability_handler,
        mock_booking_metadata_handler,
        mock_event_publisher,
        valid_booking_params,
    ):
        """Test that BookingCreated event is published"""
        # Arrange
        mock_seat_availability_handler.check_subsection_availability.return_value = True

        # Act
        await create_booking_use_case.create_booking(**valid_booking_params)

        # Assert - Event published
        mock_event_publisher.publish_booking_created.assert_awaited_once()

        # Verify the event object passed has correct type
        call_args = mock_event_publisher.publish_booking_created.call_args
        assert call_args is not None
        assert 'event' in call_args.kwargs

    @pytest.mark.asyncio
    async def test_create_booking_fail__kvrocks_save_error(
        self,
        create_booking_use_case,
        mock_seat_availability_handler,
        mock_booking_metadata_handler,
        mock_booking_command_repo,
        valid_booking_params,
    ):
        """Test booking creation fails when Kvrocks save fails"""
        # Arrange
        mock_seat_availability_handler.check_subsection_availability.return_value = True
        mock_booking_metadata_handler.save_booking_metadata.side_effect = Exception(
            'Kvrocks connection error'
        )

        # Act & Assert
        with pytest.raises(DomainError) as exc_info:
            await create_booking_use_case.create_booking(**valid_booking_params)

        assert 'Failed to save booking metadata' in str(exc_info.value)
        assert exc_info.value.status_code == 500

        # Assert - PostgreSQL was not called (fail fast)
        mock_booking_command_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_booking__manual_mode_with_seat_positions(
        self,
        create_booking_use_case,
        mock_seat_availability_handler,
        mock_booking_metadata_handler,
        valid_booking_params,
    ):
        """Test booking creation with manual seat selection mode"""
        # Arrange
        valid_booking_params['seat_selection_mode'] = 'manual'
        valid_booking_params['seat_positions'] = ['1-1', '1-2']

        mock_seat_availability_handler.check_subsection_availability.return_value = True

        # Act
        await create_booking_use_case.create_booking(**valid_booking_params)

        # Assert - Seat positions saved to metadata
        call_kwargs = mock_booking_metadata_handler.save_booking_metadata.call_args.kwargs
        assert call_kwargs['seat_selection_mode'] == 'manual'
        assert call_kwargs['seat_positions'] == ['1-1', '1-2']

    @pytest.mark.asyncio
    async def test_create_booking__sets_custom_uuid_on_booking_entity(
        self,
        create_booking_use_case,
        mock_seat_availability_handler,
        valid_booking_params,
    ):
        """Test that booking entity receives custom UUID7 id"""
        # Arrange
        mock_seat_availability_handler.check_subsection_availability.return_value = True

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
