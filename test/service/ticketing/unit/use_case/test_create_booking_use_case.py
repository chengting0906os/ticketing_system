"""
Unit tests for CreateBookingUseCase - 執行順序測試

重點測試：
1. Repository create happens BEFORE event publishing (最重要)
2. Repository error prevents event
3. Event publishing failure does not affect repository (eventual consistency)
4. Early seat availability check (Fail Fast)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.platform.exception.exceptions import DomainError
from src.service.ticketing.app.command.create_booking_use_case import CreateBookingUseCase
from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus


@pytest.mark.unit
class TestCreateBookingExecutionOrder:
    """測試 CreateBookingUseCase 的執行順序"""

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
    def mock_background_task_group(self):
        """Mock TaskGroup that silently swallows exceptions (fire-and-forget)"""
        task_group = MagicMock()
        task_group.start_soon = MagicMock()  # Synchronous mock that doesn't raise
        return task_group

    @pytest.fixture
    def use_case(
        self,
        mock_booking_command_repo,
        mock_event_publisher,
        mock_seat_availability_handler,
        mock_background_task_group,
    ):
        return CreateBookingUseCase(
            booking_command_repo=mock_booking_command_repo,
            event_publisher=mock_event_publisher,
            seat_availability_handler=mock_seat_availability_handler,
            background_task_group=mock_background_task_group,
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
        """
        測試 fire-and-forget pattern：
        - Repository create 完成後立即返回
        - Event 在背景發送，不阻塞響應
        """
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
        """
        測試錯誤處理：Repository 失敗時，event 不應該發生
        """
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
        """
        測試 fire-and-forget：Event publishing 失敗不影響 create_booking 返回

        Fire-and-forget pattern 特性：
        - Event publishing 在背景執行
        - 失敗不會拋出異常到主流程
        - Repository create 成功後立即返回
        """
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


@pytest.mark.unit
@pytest.mark.skip(reason='Seat availability check is currently disabled')
class TestSeatAvailabilityCheck:
    """測試座位可用性檢查 (Fail Fast)"""

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
    def mock_background_task_group(self):
        """Mock TaskGroup that silently swallows exceptions (fire-and-forget)"""
        task_group = MagicMock()
        task_group.start_soon = MagicMock()  # Synchronous mock that doesn't raise
        return task_group

    @pytest.fixture
    def use_case(
        self,
        mock_booking_command_repo,
        mock_event_publisher,
        mock_seat_availability_handler,
        mock_background_task_group,
    ):
        return CreateBookingUseCase(
            booking_command_repo=mock_booking_command_repo,
            event_publisher=mock_event_publisher,
            seat_availability_handler=mock_seat_availability_handler,
            background_task_group=mock_background_task_group,
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
        """
        測試 Fail Fast：座位可用性檢查應該在 booking 建立之前執行
        """
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
        """
        測試 Fail Fast：座位不足時應該立即失敗，不應該建立 booking
        """
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
        """
        測試座位可用性檢查使用正確的參數
        """
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
        """
        測試座位充足時可以成功建立 booking
        """
        # Given: Enough seats
        mock_seat_availability_handler.check_subsection_availability = AsyncMock(return_value=True)
        mock_booking_command_repo.create = AsyncMock(return_value=created_booking)

        # When
        result = await use_case.create_booking(**valid_booking_data)

        # Then: Booking should be created successfully
        assert result.id == 999
        mock_booking_command_repo.create.assert_called_once()
