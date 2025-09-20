#!/usr/bin/env python3
"""
RequestBookingUseCase 單元測試
"""

from unittest.mock import AsyncMock, patch
import uuid

import pytest

from src.booking.use_case.request_booking_use_case import RequestBookingUseCase
from src.shared.constant.topic import Topic
from src.shared.exception.exceptions import DomainError
from src.user.domain.user_model import User, UserRole


class TestRequestBookingUseCase:
    """RequestBookingUseCase 單元測試"""

    @pytest.fixture
    def mock_session(self):
        """Mock database session"""
        return AsyncMock()

    @pytest.fixture
    def mock_user_repo(self):
        """Mock user repository"""
        repo = AsyncMock()
        return repo

    @pytest.fixture
    def use_case(self, mock_session, mock_user_repo):
        """Create RequestBookingUseCase instance"""
        return RequestBookingUseCase(session=mock_session, user_repo=mock_user_repo)

    @pytest.fixture
    def valid_buyer(self):
        """Create a valid buyer user"""
        return User(
            id=1,
            email='buyer@example.com',
            hashed_password='hashed_password',
            role=UserRole.BUYER,
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )

    @pytest.mark.asyncio
    async def test_request_booking_success(self, use_case, mock_user_repo, valid_buyer):
        """測試成功的訂票請求"""
        # Arrange
        mock_user_repo.get_by_id.return_value = valid_buyer

        with patch(
            'src.booking.use_case.request_booking_use_case.publish_domain_event'
        ) as mock_publish:
            mock_publish.return_value = None

            # Act
            result = await use_case.request_booking(buyer_id=1, event_id=123, ticket_count=2)

            # Assert
            assert result['status'] == 'pending'
            assert result['buyer_id'] == 1
            assert result['event_id'] == 123
            assert result['ticket_count'] == 2
            assert 'request_id' in result
            assert len(result['request_id']) > 0

            # Verify user repo was called
            mock_user_repo.get_by_id.assert_called_once_with(user_id=1)

            # Verify event was published
            mock_publish.assert_called_once()
            call_args = mock_publish.call_args

            # Check event structure
            event = call_args.kwargs['event']
            assert event['event_type'] == 'BookingRequested'
            assert event['aggregate_id'] == 1
            assert event['data']['buyer_id'] == 1
            assert event['data']['event_id'] == 123
            assert event['data']['ticket_count'] == 2

            # Check topic and partition key
            assert call_args.kwargs['topic'] == Topic.TICKETING_BOOKING_REQUEST
            assert call_args.kwargs['partition_key'] == 'booking-requests-123'

    @pytest.mark.asyncio
    async def test_request_booking_with_seat_selection(self, use_case, mock_user_repo, valid_buyer):
        """測試帶座位選擇的訂票請求"""
        # Arrange
        mock_user_repo.get_by_id.return_value = valid_buyer

        with patch(
            'src.booking.use_case.request_booking_use_case.publish_domain_event'
        ) as mock_publish:
            mock_publish.return_value = None

            # Act
            result = await use_case.request_booking(
                buyer_id=1,
                event_id=123,
                ticket_count=2,
                seat_selection_mode='manual',
                selected_seats=['A-1-1-1', 'A-1-1-2'],
            )

            # Assert
            assert result['status'] == 'pending'

            # Verify event contains seat selection data
            mock_publish.assert_called_once()
            event = mock_publish.call_args.kwargs['event']
            assert event['data']['seat_selection_mode'] == 'manual'
            assert event['data']['selected_seats'] == ['A-1-1-1', 'A-1-1-2']

    @pytest.mark.asyncio
    async def test_request_booking_buyer_not_found(self, use_case, mock_user_repo):
        """測試買方不存在的情況"""
        # Arrange
        mock_user_repo.get_by_id.return_value = None

        # Act & Assert
        with pytest.raises(DomainError) as exc_info:
            await use_case.request_booking(buyer_id=999, event_id=123, ticket_count=2)

        assert exc_info.value.message == 'Buyer not found'
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_request_booking_invalid_ticket_count(
        self, use_case, mock_user_repo, valid_buyer
    ):
        """測試無效的票數"""
        # Arrange
        mock_user_repo.get_by_id.return_value = valid_buyer

        # Test zero tickets
        with pytest.raises(DomainError) as exc_info:
            await use_case.request_booking(buyer_id=1, event_id=123, ticket_count=0)
        assert 'must be positive' in exc_info.value.args[0]

        # Test too many tickets
        with pytest.raises(DomainError) as exc_info:
            await use_case.request_booking(buyer_id=1, event_id=123, ticket_count=5)
        assert 'Maximum 4 tickets' in exc_info.value.args[0]

    @pytest.mark.asyncio
    async def test_request_booking_event_publish_failure(
        self, use_case, mock_user_repo, valid_buyer
    ):
        """測試事件發布失敗的情況"""
        # Arrange
        mock_user_repo.get_by_id.return_value = valid_buyer

        with patch(
            'src.booking.use_case.request_booking_use_case.publish_domain_event'
        ) as mock_publish:
            mock_publish.side_effect = Exception('Kafka connection failed')

            # Act & Assert
            with pytest.raises(Exception) as exc_info:
                await use_case.request_booking(buyer_id=1, event_id=123, ticket_count=2)

            assert 'Kafka connection failed' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_request_id_uniqueness(self, use_case, mock_user_repo, valid_buyer):
        """測試每次請求生成的 request_id 都是唯一的"""
        # Arrange
        mock_user_repo.get_by_id.return_value = valid_buyer

        with patch(
            'src.booking.use_case.request_booking_use_case.publish_domain_event'
        ) as mock_publish:
            mock_publish.return_value = None

            # Act - 發送兩次請求
            result1 = await use_case.request_booking(buyer_id=1, event_id=123, ticket_count=2)

            result2 = await use_case.request_booking(buyer_id=1, event_id=123, ticket_count=2)

            # Assert - request_id 應該不同
            assert result1['request_id'] != result2['request_id']
            assert uuid.UUID(result1['request_id'])  # 驗證是有效的 UUID
            assert uuid.UUID(result2['request_id'])  # 驗證是有效的 UUID
