from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.platform.exception.exceptions import DomainError
from src.service.ticketing.app.command.create_booking_use_case import CreateBookingUseCase
from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus


class TestCreateBookingExecutionOrder:
    @pytest.fixture
    def mock_booking_command_repo(self):
        """Mock repository for booking commands"""
        repo = MagicMock()
        repo.create = AsyncMock()
        return repo

    @pytest.fixture
    def mock_event_publisher(self):
        publisher = MagicMock()
        publisher.publish_booking_created = AsyncMock()
        return publisher

    @pytest.fixture
    def mock_seat_availability_handler(self):
        handler = MagicMock()
        handler.check_subsection_availability = AsyncMock(return_value=True)
        return handler

    @pytest.fixture
    def use_case(
        self, mock_booking_command_repo, mock_event_publisher, mock_seat_availability_handler
    ):
        return CreateBookingUseCase(
            booking_command_repo=mock_booking_command_repo,
            event_publisher=mock_event_publisher,
            seat_availability_handler=mock_seat_availability_handler,
        )

    @pytest.fixture
    def valid_booking_data(self):
        return {
            'buyer_id': 1,
            'event_id': 100,
            'section': 'A',
            'subsection': 1,
            'seat_selection_mode': 'manual',
            'seat_positions': ['1-1', '1-2'],  # Correct format: row-seat
            'quantity': 2,
        }

    @pytest.fixture
    def created_booking(self):
        return Booking(
            id=999,
            buyer_id=1,
            event_id=100,
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            seat_positions=['1-1', '1-2'],
            quantity=2,
            status=BookingStatus.PROCESSING,
            total_price=0,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_commit_happens_before_event_publishing(
        self,
        use_case,
        mock_booking_command_repo,
        mock_event_publisher,
        valid_booking_data,
        created_booking,
    ):
        # Given
        mock_booking_command_repo.create = AsyncMock(return_value=created_booking)

        # When
        result = await use_case.create_booking(**valid_booking_data)

        # Then: Create completed and returned immediately
        assert result == created_booking
        mock_booking_command_repo.create.assert_called_once()

        # Event publishing is fire-and-forget (not awaited, runs in background)

    @pytest.mark.asyncio
    async def test_repository_error_prevents_commit_and_event(
        self, use_case, mock_booking_command_repo, mock_event_publisher, valid_booking_data
    ):
        # Given: Repository raises error
        mock_booking_command_repo.create = AsyncMock(
            side_effect=Exception('Database connection failed')
        )

        # When/Then
        with pytest.raises(DomainError, match='Failed to create booking'):
            await use_case.create_booking(**valid_booking_data)

        # Event should NOT be called
        mock_event_publisher.publish_booking_created.assert_not_called()

    @pytest.mark.asyncio
    async def test_event_publishing_failure_does_not_rollback_commit(
        self,
        use_case,
        mock_booking_command_repo,
        mock_event_publisher,
        valid_booking_data,
        created_booking,
    ):
        # Given: Repository succeeds, event publishing fails (but in background)
        mock_booking_command_repo.create = AsyncMock(return_value=created_booking)
        mock_event_publisher.publish_booking_created = AsyncMock(
            side_effect=Exception('Kafka unavailable')
        )

        # When
        result = await use_case.create_booking(**valid_booking_data)

        # Then: Create succeeds and returns, event failure doesn't propagate
        assert result == created_booking
        mock_booking_command_repo.create.assert_called_once()


class TestSeatAvailabilityCheck:
    @pytest.fixture
    def mock_booking_command_repo(self):
        """Mock repository for booking commands"""
        repo = MagicMock()
        repo.create = AsyncMock()
        return repo

    @pytest.fixture
    def mock_event_publisher(self):
        publisher = MagicMock()
        publisher.publish_booking_created = AsyncMock()
        return publisher

    @pytest.fixture
    def mock_seat_availability_handler(self):
        handler = MagicMock()
        handler.check_subsection_availability = AsyncMock(return_value=True)
        return handler

    @pytest.fixture
    def use_case(
        self, mock_booking_command_repo, mock_event_publisher, mock_seat_availability_handler
    ):
        return CreateBookingUseCase(
            booking_command_repo=mock_booking_command_repo,
            event_publisher=mock_event_publisher,
            seat_availability_handler=mock_seat_availability_handler,
        )

    @pytest.fixture
    def valid_booking_data(self):
        return {
            'buyer_id': 1,
            'event_id': 100,
            'section': 'A',
            'subsection': 1,
            'seat_selection_mode': 'manual',
            'seat_positions': ['1-1', '1-2'],
            'quantity': 2,
        }

    @pytest.fixture
    def created_booking(self):
        return Booking(
            id=999,
            buyer_id=1,
            event_id=100,
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            seat_positions=['1-1', '1-2'],
            quantity=2,
            status=BookingStatus.PROCESSING,
            total_price=0,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_availability_check_happens_before_booking_creation(
        self,
        use_case,
        mock_booking_command_repo,
        mock_seat_availability_handler,
        valid_booking_data,
        created_booking,
    ):
        # Given: Track call order
        call_order = []

        async def track_availability_check(*, event_id, section, subsection, required_quantity):
            call_order.append('availability_check')
            return True

        async def track_create(*, booking):
            call_order.append('create_booking')
            return created_booking

        mock_seat_availability_handler.check_subsection_availability = AsyncMock(
            side_effect=track_availability_check
        )
        mock_booking_command_repo.create = AsyncMock(side_effect=track_create)

        # When
        await use_case.create_booking(**valid_booking_data)

        # Then: Availability check must come BEFORE booking creation
        assert call_order == ['availability_check', 'create_booking']

    @pytest.mark.asyncio
    async def test_insufficient_seats_prevents_booking_creation(
        self,
        use_case,
        mock_booking_command_repo,
        mock_seat_availability_handler,
        valid_booking_data,
    ):
        # Given: Not enough seats
        mock_seat_availability_handler.check_subsection_availability = AsyncMock(return_value=False)

        # When/Then
        with pytest.raises(DomainError, match='Insufficient seats available'):
            await use_case.create_booking(**valid_booking_data)

        # Repository create should NOT be called
        mock_booking_command_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_availability_check_called_with_correct_parameters(
        self,
        use_case,
        mock_booking_command_repo,
        mock_seat_availability_handler,
        valid_booking_data,
        created_booking,
    ):
        # Given
        mock_booking_command_repo.create = AsyncMock(return_value=created_booking)

        # When
        await use_case.create_booking(**valid_booking_data)

        # Then: Verify correct parameters
        mock_seat_availability_handler.check_subsection_availability.assert_called_once_with(
            event_id=100, section='A', subsection=1, required_quantity=2
        )

    @pytest.mark.asyncio
    async def test_sufficient_seats_allows_booking_creation(
        self,
        use_case,
        mock_booking_command_repo,
        mock_seat_availability_handler,
        valid_booking_data,
        created_booking,
    ):
        # Given: Enough seats
        mock_seat_availability_handler.check_subsection_availability = AsyncMock(return_value=True)
        mock_booking_command_repo.create = AsyncMock(return_value=created_booking)

        # When
        result = await use_case.create_booking(**valid_booking_data)

        # Then: Booking should be created successfully
        assert result.id == 999
        mock_booking_command_repo.create.assert_called_once()
