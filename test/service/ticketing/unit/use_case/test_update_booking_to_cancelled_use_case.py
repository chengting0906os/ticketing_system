"""
Unit tests for UpdateBookingToCancelledUseCase

測試重點：
1. Domain 驗證：只有 PROCESSING/PENDING_PAYMENT 可取消
2. Event 發送：取消後發送 BookingCancelledEvent 釋放座位
3. Fail Fast: booking 不存在、權限不符、狀態不允許
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.platform.exception.exceptions import DomainError, ForbiddenError, NotFoundError
from src.service.ticketing.app.command.update_booking_status_to_cancelled_use_case import (
    UpdateBookingToCancelledUseCase,
)
from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import Ticket, TicketStatus
from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus
from test.service.ticketing.unit.test_helpers import RepositoryMocks


class TestUpdateBookingToCancelled:
    """測試更新 booking 到 cancelled 狀態"""

    @pytest.fixture
    def pending_payment_booking(self):
        """待付款的 booking（可取消）"""
        return Booking(
            id=10,
            buyer_id=2,
            event_id=1,
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            seat_positions=['1-1', '1-2'],
            quantity=2,
            status=BookingStatus.PENDING_PAYMENT,
            total_price=3000,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def reserved_tickets(self):
        """兩張已預訂的票券"""
        return [
            Ticket(
                id=201,
                event_id=1,
                section='A',
                subsection=1,
                row=1,
                seat=1,
                price=1500,
                status=TicketStatus.RESERVED,
                buyer_id=2,
            ),
            Ticket(
                id=202,
                event_id=1,
                section='A',
                subsection=1,
                row=1,
                seat=2,
                price=1500,
                status=TicketStatus.RESERVED,
                buyer_id=2,
            ),
        ]

    @pytest.mark.asyncio
    @patch(
        'src.service.ticketing.app.command.update_booking_status_to_cancelled_use_case.publish_domain_event'
    )
    async def test_successfully_cancel_pending_payment_booking(
        self, mock_publish, pending_payment_booking, reserved_tickets
    ):
        """
        核心測試：成功取消待付款訂單

        Given: PENDING_PAYMENT 狀態的 booking
        When: buyer 執行取消操作
        Then:
          - booking 狀態變為 CANCELLED
          - 發送 BookingCancelledEvent
          - event 包含 ticket_ids 和 seat_positions
        """
        # Arrange
        cancelled_booking = pending_payment_booking.cancel()
        repo_mocks = RepositoryMocks(
            booking=pending_payment_booking,
            tickets=reserved_tickets,
            ticket_ids=[201, 202],
        )
        repo_mocks.booking_command_repo.update_status_to_cancelled = AsyncMock(
            return_value=cancelled_booking
        )
        repo_mocks.event_ticketing_query_repo.get_tickets_by_ids = AsyncMock(
            return_value=reserved_tickets
        )

        use_case = UpdateBookingToCancelledUseCase(
            booking_command_repo=repo_mocks.booking_command_repo,
            event_ticketing_query_repo=repo_mocks.event_ticketing_query_repo,
        )

        # Act
        result = await use_case.execute(booking_id=10, buyer_id=2)

        # Assert
        assert result.status == BookingStatus.CANCELLED
        assert result.id == 10

        # 驗證發送了 event
        mock_publish.assert_called_once()
        call_args = mock_publish.call_args
        event = call_args.kwargs['event']
        assert event.booking_id == 10
        assert event.buyer_id == 2
        assert event.event_id == 1
        assert event.ticket_ids == [201, 202]
        assert len(event.seat_positions) == 2

    @pytest.mark.asyncio
    async def test_fail_when_booking_not_found(self):
        """
        Fail Fast: booking 不存在

        Given: 不存在的 booking_id
        When: 執行取消操作
        Then: 拋出 NotFoundError
        """
        # Arrange
        repo_mocks = RepositoryMocks(booking=None)
        use_case = UpdateBookingToCancelledUseCase(
            booking_command_repo=repo_mocks.booking_command_repo,
            event_ticketing_query_repo=repo_mocks.event_ticketing_query_repo,
        )

        # Act & Assert
        with pytest.raises(NotFoundError, match='Booking not found'):
            await use_case.execute(booking_id=999, buyer_id=2)

    @pytest.mark.asyncio
    async def test_fail_when_not_booking_owner(self, pending_payment_booking):
        """
        Fail Fast: 非訂單擁有者

        Given: buyer_id=2 的 booking
        When: buyer_id=3 嘗試取消
        Then: 拋出 ForbiddenError
        """
        # Arrange
        repo_mocks = RepositoryMocks(booking=pending_payment_booking)
        use_case = UpdateBookingToCancelledUseCase(
            booking_command_repo=repo_mocks.booking_command_repo,
            event_ticketing_query_repo=repo_mocks.event_ticketing_query_repo,
        )

        # Act & Assert
        with pytest.raises(ForbiddenError, match='Only the buyer can cancel this booking'):
            await use_case.execute(booking_id=10, buyer_id=3)  # 不同的 buyer_id

    @pytest.mark.asyncio
    async def test_fail_when_booking_already_completed(self):
        """
        Domain 驗證：已完成的訂單不能取消

        Given: COMPLETED 狀態的 booking
        When: 執行取消操作
        Then: 拋出 DomainError
        """
        # Arrange
        completed_booking = Booking(
            id=11,
            buyer_id=2,
            event_id=1,
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            seat_positions=['1-1'],
            quantity=1,
            status=BookingStatus.COMPLETED,
            total_price=1500,
            paid_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        repo_mocks = RepositoryMocks(booking=completed_booking)
        use_case = UpdateBookingToCancelledUseCase(
            booking_command_repo=repo_mocks.booking_command_repo,
            event_ticketing_query_repo=repo_mocks.event_ticketing_query_repo,
        )

        # Act & Assert
        with pytest.raises(DomainError, match='Cannot cancel completed booking'):
            await use_case.execute(booking_id=11, buyer_id=2)

    @pytest.mark.asyncio
    async def test_fail_when_booking_already_cancelled(self):
        """
        Domain 驗證：已取消的訂單不能再次取消

        Given: CANCELLED 狀態的 booking
        When: 執行取消操作
        Then: 拋出 DomainError
        """
        # Arrange
        cancelled_booking = Booking(
            id=12,
            buyer_id=2,
            event_id=1,
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            seat_positions=['1-1'],
            quantity=1,
            status=BookingStatus.CANCELLED,
            total_price=1500,
            created_at=datetime.now(timezone.utc),
        )
        repo_mocks = RepositoryMocks(booking=cancelled_booking)
        use_case = UpdateBookingToCancelledUseCase(
            booking_command_repo=repo_mocks.booking_command_repo,
            event_ticketing_query_repo=repo_mocks.event_ticketing_query_repo,
        )

        # Act & Assert
        with pytest.raises(DomainError, match='Booking already cancelled'):
            await use_case.execute(booking_id=12, buyer_id=2)

    @pytest.mark.asyncio
    @patch(
        'src.service.ticketing.app.command.update_booking_status_to_cancelled_use_case.publish_domain_event'
    )
    async def test_event_contains_correct_seat_positions(
        self, mock_publish, pending_payment_booking
    ):
        """
        Event 內容驗證：seat_positions 正確提取

        Given: booking 關聯 2 張有座位號的票
        When: 取消訂單
        Then: event 的 seat_positions 包含正確的座位識別符
        """
        # Arrange
        tickets_with_seats = [
            Ticket(
                id=201,
                event_id=1,
                section='A',
                subsection=1,
                row=1,
                seat=1,
                price=1500,
                status=TicketStatus.RESERVED,
                buyer_id=2,
            ),
            Ticket(
                id=202,
                event_id=1,
                section='A',
                subsection=1,
                row=1,
                seat=2,
                price=1500,
                status=TicketStatus.RESERVED,
                buyer_id=2,
            ),
        ]

        cancelled_booking = pending_payment_booking.cancel()
        repo_mocks = RepositoryMocks(
            booking=pending_payment_booking,
            tickets=tickets_with_seats,
            ticket_ids=[201, 202],
        )
        repo_mocks.booking_command_repo.update_status_to_cancelled = AsyncMock(
            return_value=cancelled_booking
        )
        repo_mocks.event_ticketing_query_repo.get_tickets_by_ids = AsyncMock(
            return_value=tickets_with_seats
        )

        use_case = UpdateBookingToCancelledUseCase(
            booking_command_repo=repo_mocks.booking_command_repo,
            event_ticketing_query_repo=repo_mocks.event_ticketing_query_repo,
        )

        # Act
        await use_case.execute(booking_id=10, buyer_id=2)

        # Assert
        mock_publish.assert_called_once()
        event = mock_publish.call_args.kwargs['event']

        # seat_identifier 格式為 "A-1-1-1" (section-subsection-row-seat)
        expected_seat_ids = ['A-1-1-1', 'A-1-1-2']
        assert event.seat_positions == expected_seat_ids

    @pytest.mark.asyncio
    @patch(
        'src.service.ticketing.app.command.update_booking_status_to_cancelled_use_case.publish_domain_event'
    )
    async def test_no_event_published_when_no_tickets(self, mock_publish, pending_payment_booking):
        """
        邊界測試：沒有票券時不發送 event

        Given: booking 沒有關聯任何票券
        When: 取消訂單
        Then: 不發送 event
        """
        # Arrange
        cancelled_booking = pending_payment_booking.cancel()
        repo_mocks = RepositoryMocks(
            booking=pending_payment_booking,
            tickets=[],
            ticket_ids=[],
        )
        repo_mocks.booking_command_repo.update_status_to_cancelled = AsyncMock(
            return_value=cancelled_booking
        )

        use_case = UpdateBookingToCancelledUseCase(
            booking_command_repo=repo_mocks.booking_command_repo,
            event_ticketing_query_repo=repo_mocks.event_ticketing_query_repo,
        )

        # Act
        result = await use_case.execute(booking_id=10, buyer_id=2)

        # Assert
        assert result.status == BookingStatus.CANCELLED
        mock_publish.assert_not_called()  # 沒有票券，不發送 event
