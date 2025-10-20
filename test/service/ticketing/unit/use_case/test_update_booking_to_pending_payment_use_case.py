"""
Unit tests for UpdateBookingToPendingPaymentAndTicketToReservedUseCase

測試重點：
1. total_price 正確計算並更新到 booking
2. 執行順序：查詢 booking → 更新 tickets → 計算價格 → 更新 booking → commit
3. Fail Fast: ticket_ids 數量不符、booking 不存在、權限不符
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.platform.exception.exceptions import ForbiddenError, NotFoundError
from src.service.ticketing.app.command.update_booking_status_to_pending_payment_and_ticket_to_reserved_use_case import (
    UpdateBookingToPendingPaymentAndTicketToReservedUseCase,
)
from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import Ticket, TicketStatus
from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus
from test.service.ticketing.unit.test_helpers import RepositoryMocks


class TestUpdateBookingToPendingPayment:
    """測試更新 booking 到 pending_payment 狀態"""

    @pytest.fixture
    def existing_booking(self):
        """現有的 processing 狀態 booking"""
        return Booking(
            id=4,
            buyer_id=2,
            event_id=1,
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            seat_positions=['1-1', '1-2'],
            quantity=2,
            status=BookingStatus.PROCESSING,
            total_price=0,  # 初始為 0
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def reserved_tickets(self):
        """兩張已預訂的票券"""
        return [
            Ticket(
                id=101,
                event_id=1,
                section='A',
                subsection=1,
                row=1,
                seat=1,
                price=1500,  # 票價 1500
                status=TicketStatus.RESERVED,
                buyer_id=2,
            ),
            Ticket(
                id=102,
                event_id=1,
                section='A',
                subsection=1,
                row=1,
                seat=2,
                price=1500,  # 票價 1500
                status=TicketStatus.RESERVED,
                buyer_id=2,
            ),
        ]

    @pytest.mark.asyncio
    async def test_total_price_calculated_correctly(self, existing_booking, reserved_tickets):
        """
        核心測試：驗證 total_price 計算正確

        Given: 2 張票券，每張 1500
        When: 執行 use case
        Then: total_price = 3000
        """
        # Given
        repo_mocks = RepositoryMocks(
            booking=existing_booking,
            tickets=reserved_tickets,
            ticket_ids=[101, 102],
        )
        use_case = UpdateBookingToPendingPaymentAndTicketToReservedUseCase(
            booking_command_repo=repo_mocks.booking_command_repo,
            event_ticketing_command_repo=repo_mocks.event_ticketing_command_repo,
        )

        # When
        result = await use_case.execute(
            booking_id=4,
            buyer_id=2,
            seat_identifiers=['A-1-1-1', 'A-1-1-2'],
        )

        # Then
        assert result.total_price == 3000
        assert result.status == BookingStatus.PENDING_PAYMENT
        assert result.seat_positions == ['A-1-1-1', 'A-1-1-2']

    @pytest.mark.asyncio
    async def test_execution_order(self, existing_booking, reserved_tickets):
        """
        測試執行順序：
        1. 查詢 booking
        2. 轉換 seat_identifiers → ticket_ids
        3. 更新 tickets 狀態
        4. 查詢 tickets 計算價格
        5. 更新 booking 狀態
        6. 建立關聯
        7. commit
        """
        # Given: Track call order
        call_order = []
        repo_mocks = RepositoryMocks(
            booking=existing_booking,
            tickets=reserved_tickets,
            ticket_ids=[101, 102],
        )

        # Override methods to track call order
        original_get_booking = repo_mocks.booking_command_repo.get_by_id
        original_get_ticket_ids = (
            repo_mocks.event_ticketing_command_repo.get_ticket_ids_by_seat_identifiers
        )
        original_update_tickets = repo_mocks.event_ticketing_command_repo.update_tickets_status
        original_get_tickets = repo_mocks.event_ticketing_query_repo.get_tickets_by_ids
        original_update_booking = repo_mocks.booking_command_repo.update_status_to_pending_payment

        async def track_get_booking(*args, **kwargs):
            call_order.append('get_booking')
            return await original_get_booking(*args, **kwargs)

        async def track_get_ticket_ids(*args, **kwargs):
            call_order.append('get_ticket_ids')
            return await original_get_ticket_ids(*args, **kwargs)

        async def track_update_tickets(*args, **kwargs):
            call_order.append('update_tickets')
            return await original_update_tickets(*args, **kwargs)

        async def track_get_tickets(*args, **kwargs):
            call_order.append('get_tickets_for_price')
            return await original_get_tickets(*args, **kwargs)

        async def track_update_booking(*args, **kwargs):
            call_order.append('update_booking')
            result = await original_update_booking(*args, **kwargs)
            # 驗證 booking 已經被正確更新
            booking = kwargs.get('booking')
            assert booking.status == BookingStatus.PENDING_PAYMENT
            assert booking.total_price == 3000
            assert booking.seat_positions == ['A-1-1-1', 'A-1-1-2']
            return result

        repo_mocks.booking_command_repo.get_by_id = AsyncMock(side_effect=track_get_booking)
        repo_mocks.event_ticketing_command_repo.get_ticket_ids_by_seat_identifiers = AsyncMock(
            side_effect=track_get_ticket_ids
        )
        repo_mocks.event_ticketing_command_repo.update_tickets_status = AsyncMock(
            side_effect=track_update_tickets
        )
        repo_mocks.event_ticketing_command_repo.get_tickets_by_ids = AsyncMock(
            side_effect=track_get_tickets
        )
        repo_mocks.booking_command_repo.update_status_to_pending_payment = AsyncMock(
            side_effect=track_update_booking
        )

        use_case = UpdateBookingToPendingPaymentAndTicketToReservedUseCase(
            booking_command_repo=repo_mocks.booking_command_repo,
            event_ticketing_command_repo=repo_mocks.event_ticketing_command_repo,
        )

        # When
        await use_case.execute(
            booking_id=4,
            buyer_id=2,
            seat_identifiers=['A-1-1-1', 'A-1-1-2'],
        )

        # Then: 驗證執行順序（asyncpg autocommit，不再需要明確 commit）
        # Note: No longer need to link tickets to booking mapping table
        expected_order = [
            'get_booking',
            'get_ticket_ids',
            'update_tickets',
            'get_tickets_for_price',
            'update_booking',
        ]
        assert call_order == expected_order

    @pytest.mark.asyncio
    async def test_fail_fast_booking_not_found(self):
        """
        Fail Fast 測試：booking 不存在

        Given: booking 不存在（get_by_id 返回 None）
        When: 執行 use case
        Then: 拋出 NotFoundError
        """
        # Given
        repo_mocks = RepositoryMocks(booking=None)  # 不存在的 booking
        use_case = UpdateBookingToPendingPaymentAndTicketToReservedUseCase(
            booking_command_repo=repo_mocks.booking_command_repo,
            event_ticketing_command_repo=repo_mocks.event_ticketing_command_repo,
        )

        # When/Then
        with pytest.raises(NotFoundError, match='Booking not found'):
            await use_case.execute(
                booking_id=999,
                buyer_id=2,
                seat_identifiers=['A-1-1-1'],
            )

    @pytest.mark.asyncio
    async def test_fail_fast_forbidden_buyer(self, existing_booking):
        """
        Fail Fast 測試：buyer 不匹配

        Given: booking.buyer_id = 2
        When: 使用 buyer_id = 3 執行
        Then: 拋出 ForbiddenError
        """
        # Given
        repo_mocks = RepositoryMocks(booking=existing_booking)
        use_case = UpdateBookingToPendingPaymentAndTicketToReservedUseCase(
            booking_command_repo=repo_mocks.booking_command_repo,
            event_ticketing_command_repo=repo_mocks.event_ticketing_command_repo,
        )

        # When/Then
        with pytest.raises(ForbiddenError, match='Booking owner mismatch'):
            await use_case.execute(
                booking_id=4,
                buyer_id=3,  # 錯誤的 buyer_id
                seat_identifiers=['A-1-1-1', 'A-1-1-2'],
            )
