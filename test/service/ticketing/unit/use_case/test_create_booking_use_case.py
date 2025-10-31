"""
Unit tests for CreateBookingUseCase

Tests the optimized booking creation flow:
1. UUID7 generation
2. Kvrocks metadata storage
3. PostgreSQL persistence
4. Kafka event publishing
"""

from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import UUID7 as UUID
import pytest

from src.platform.exception.exceptions import DomainError
from src.service.ticketing.app.command.create_booking_use_case import CreateBookingUseCase
from src.service.ticketing.domain.entity.booking_entity import Booking


@pytest.fixture
def mock_task_group():
    """Mock anyio task group for testing"""
    task_group = MagicMock()
    task_group.start_soon = MagicMock()
    return task_group


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
    mock_task_group,
):
    """Create instance of CreateBookingUseCase with mocked dependencies"""
    return CreateBookingUseCase(
        booking_metadata_handler=mock_booking_metadata_handler,
        booking_command_repo=mock_booking_command_repo,
        event_publisher=mock_event_publisher,
        seat_availability_handler=mock_seat_availability_handler,
        task_group=mock_task_group,
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

        # Create a mock booking with UUID7 ID
        mock_booking = MagicMock(spec=Booking)
        mock_booking.id = None  # Will be set by use case
        mock_booking_command_repo.create.return_value = mock_booking

        # Act
        with patch(
            'src.service.ticketing.app.command.create_booking_use_case.uuid.uuid7'
        ) as mock_uuid7:
            test_uuid = UUID('01936d8f-5e73-7c4e-a9c5-123456789abc')  # Valid UUID7
            mock_uuid7.return_value = test_uuid

            await create_booking_use_case.create_booking(**valid_booking_params)

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

        # Assert - Booking saved to PostgreSQL
        mock_booking_command_repo.create.assert_awaited_once()

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
    async def test_create_booking_fail__kvrocks_error_cleanup(
        self,
        create_booking_use_case,
        mock_seat_availability_handler,
        mock_booking_metadata_handler,
        mock_booking_command_repo,
        valid_booking_params,
    ):
        """Test Kvrocks metadata cleanup when PostgreSQL fails"""
        # Arrange
        mock_seat_availability_handler.check_subsection_availability.return_value = True
        mock_booking_metadata_handler.save_booking_metadata.return_value = None  # Success
        mock_booking_command_repo.create.side_effect = Exception('Database connection error')

        # Act & Assert
        with pytest.raises(DomainError) as exc_info:
            await create_booking_use_case.create_booking(**valid_booking_params)

        assert 'Failed to create booking' in str(exc_info.value)

        # Assert - Cleanup was attempted
        mock_booking_metadata_handler.delete_booking_metadata.assert_awaited_once()

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
        mock_booking_command_repo,
        valid_booking_params,
    ):
        """Test booking creation with manual seat selection mode"""
        # Arrange
        valid_booking_params['seat_selection_mode'] = 'manual'
        valid_booking_params['seat_positions'] = ['1-1', '1-2']

        mock_seat_availability_handler.check_subsection_availability.return_value = True
        mock_booking = MagicMock(spec=Booking)
        mock_booking.id = 'test-uuid'
        mock_booking_command_repo.create.return_value = mock_booking

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
        mock_booking_command_repo,
        valid_booking_params,
    ):
        """Test that booking entity receives custom UUID7 id"""
        # Arrange
        mock_seat_availability_handler.check_subsection_availability.return_value = True

        captured_booking = None

        async def capture_booking(booking):
            nonlocal captured_booking
            captured_booking = booking
            return booking

        mock_booking_command_repo.create.side_effect = capture_booking

        # Act
        with patch(
            'src.service.ticketing.app.command.create_booking_use_case.uuid.uuid7'
        ) as mock_uuid7:
            test_uuid = UUID('01936d8f-5e73-7c4e-a9c5-123456789abc')
            mock_uuid7.return_value = test_uuid

            await create_booking_use_case.create_booking(**valid_booking_params)

        # Assert - Booking entity has UUID7 as id
        assert captured_booking is not None
        assert captured_booking.id == test_uuid  # UUID object, not string
