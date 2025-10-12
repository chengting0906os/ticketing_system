"""
Unit tests for CreateBookingUseCase - 執行順序測試

重點測試：
1. Commit happens BEFORE event publishing (最重要)
2. Repository error prevents commit and event
3. Event publishing failure does not rollback (eventual consistency)
4. Early seat availability check (Fail Fast)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.platform.exception.exceptions import DomainError
from src.service.ticketing.app.command.create_booking_use_case import CreateBookingUseCase
from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus


class TestCreateBookingExecutionOrder:
    """測試 CreateBookingUseCase 的執行順序"""

    @pytest.fixture
    def mock_uow(self):
        uow = MagicMock()
        uow.booking_command_repo = MagicMock()
        uow.commit = AsyncMock()
        uow.__aenter__ = AsyncMock(return_value=uow)
        uow.__aexit__ = AsyncMock(return_value=None)
        return uow

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
    def use_case(self, mock_uow, mock_event_publisher, mock_seat_availability_handler):
        return CreateBookingUseCase(
            uow=mock_uow,
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
        self, use_case, mock_uow, mock_event_publisher, valid_booking_data, created_booking
    ):
        """
        ⭐ 最重要的測試 ⭐
        確保 commit 發生在 event publishing 之前
        防止發送未提交資料的事件
        """
        # Given: Track call order
        call_order = []

        async def track_commit():
            call_order.append('commit')

        async def track_publish(*, event):
            call_order.append('publish_event')

        mock_uow.booking_command_repo.create = AsyncMock(return_value=created_booking)
        mock_uow.commit = AsyncMock(side_effect=track_commit)
        mock_event_publisher.publish_booking_created = AsyncMock(side_effect=track_publish)

        # When
        await use_case.create_booking(**valid_booking_data)

        # Then: Commit must come BEFORE event publishing
        assert call_order == ['commit', 'publish_event']

    @pytest.mark.asyncio
    async def test_repository_error_prevents_commit_and_event(
        self, use_case, mock_uow, mock_event_publisher, valid_booking_data
    ):
        """
        測試錯誤處理：Repository 失敗時，commit 和 event 都不應該發生
        """
        # Given: Repository raises error
        mock_uow.booking_command_repo.create = AsyncMock(
            side_effect=Exception('Database connection failed')
        )

        # When/Then
        with pytest.raises(DomainError, match='Database connection failed'):
            await use_case.create_booking(**valid_booking_data)

        # Commit and event should NOT be called
        mock_uow.commit.assert_not_called()
        mock_event_publisher.publish_booking_created.assert_not_called()

    @pytest.mark.asyncio
    async def test_event_publishing_failure_does_not_rollback_commit(
        self, use_case, mock_uow, mock_event_publisher, valid_booking_data, created_booking
    ):
        """
        測試最終一致性：Event publishing 失敗時，transaction 已經 committed
        這是刻意的設計 - 接受最終一致性而非分散式交易
        """
        # Given: Repository succeeds, event publishing fails
        mock_uow.booking_command_repo.create = AsyncMock(return_value=created_booking)
        mock_event_publisher.publish_booking_created = AsyncMock(
            side_effect=Exception('Kafka unavailable')
        )

        # When/Then
        with pytest.raises(Exception, match='Kafka unavailable'):
            await use_case.create_booking(**valid_booking_data)

        # Commit should have succeeded (eventual consistency)
        mock_uow.commit.assert_called_once()


class TestSeatAvailabilityCheck:
    """測試座位可用性檢查 (Fail Fast)"""

    @pytest.fixture
    def mock_uow(self):
        uow = MagicMock()
        uow.booking_command_repo = MagicMock()
        uow.commit = AsyncMock()
        uow.__aenter__ = AsyncMock(return_value=uow)
        uow.__aexit__ = AsyncMock(return_value=None)
        return uow

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
    def use_case(self, mock_uow, mock_event_publisher, mock_seat_availability_handler):
        return CreateBookingUseCase(
            uow=mock_uow,
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
        mock_uow,
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
        mock_uow.booking_command_repo.create = AsyncMock(side_effect=track_create)

        # When
        await use_case.create_booking(**valid_booking_data)

        # Then: Availability check must come BEFORE booking creation
        assert call_order == ['availability_check', 'create_booking']

    @pytest.mark.asyncio
    async def test_insufficient_seats_prevents_booking_creation(
        self, use_case, mock_uow, mock_seat_availability_handler, valid_booking_data
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
        mock_uow.booking_command_repo.create.assert_not_called()
        mock_uow.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_availability_check_called_with_correct_parameters(
        self,
        use_case,
        mock_uow,
        mock_seat_availability_handler,
        valid_booking_data,
        created_booking,
    ):
        """
        測試座位可用性檢查使用正確的參數
        """
        # Given
        mock_uow.booking_command_repo.create = AsyncMock(return_value=created_booking)

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
        mock_uow,
        mock_seat_availability_handler,
        valid_booking_data,
        created_booking,
    ):
        """
        測試座位充足時可以成功建立 booking
        """
        # Given: Enough seats
        mock_seat_availability_handler.check_subsection_availability = AsyncMock(return_value=True)
        mock_uow.booking_command_repo.create = AsyncMock(return_value=created_booking)

        # When
        result = await use_case.create_booking(**valid_booking_data)

        # Then: Booking should be created successfully
        assert result.id == 999
        mock_uow.booking_command_repo.create.assert_called_once()
        mock_uow.commit.assert_called_once()
