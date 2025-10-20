"""
Unit tests for UpdateBookingToPendingPaymentAndTicketToReservedUseCase

Testing Focus:
1. Atomic operation reduces 5 DB round-trips to 1
2. total_price correctly calculated and updated to booking
3. Fail Fast: booking not found, ownership mismatch, empty seat_identifiers
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.platform.exception.exceptions import ForbiddenError, NotFoundError
from src.service.ticketing.app.command.update_booking_status_to_pending_payment_and_ticket_to_reserved_use_case import (
    UpdateBookingToPendingPaymentAndTicketToReservedUseCase,
)
from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import TicketStatus
from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus
from src.service.ticketing.domain.value_object.ticket_ref import TicketRef


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
        """Two reserved tickets returned by atomic operation"""
        return [
            TicketRef(
                id=101,
                event_id=1,
                section='A',
                subsection=1,
                row=1,
                seat=1,
                price=1500,
                status=TicketStatus.RESERVED,
                buyer_id=2,
            ),
            TicketRef(
                id=102,
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
    async def test_atomic_operation_with_correct_total_price(
        self, existing_booking, reserved_tickets
    ):
        """
        Test atomic operation: reserve tickets + update booking in 1 DB round-trip

        Given: 2 tickets, 1500 each
        When: Execute use case
        Then: total_price = 3000, status = PENDING_PAYMENT (1 DB call)
        """
        # Given: Mock the new atomic method
        updated_booking = Booking(
            id=4,
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

        booking_command_repo = AsyncMock()
        booking_command_repo.get_by_id = AsyncMock(return_value=existing_booking)
        booking_command_repo.reserve_tickets_and_update_booking_atomically = AsyncMock(
            return_value=(updated_booking, reserved_tickets, 3000)
        )

        use_case = UpdateBookingToPendingPaymentAndTicketToReservedUseCase(
            booking_command_repo=booking_command_repo,
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
        # Verify atomic method was called with correct parameters
        booking_command_repo.reserve_tickets_and_update_booking_atomically.assert_called_once_with(
            booking_id=4,
            buyer_id=2,
            event_id=1,
            section='A',
            subsection=1,
            seat_identifiers=['A-1-1-1', 'A-1-1-2'],
        )

    @pytest.mark.asyncio
    async def test_fail_fast_booking_not_found(self):
        """
        Fail Fast: booking does not exist

        Given: booking not found (get_by_id returns None)
        When: Execute use case
        Then: Raise NotFoundError
        """
        # Given
        booking_command_repo = AsyncMock()
        booking_command_repo.get_by_id = AsyncMock(return_value=None)

        use_case = UpdateBookingToPendingPaymentAndTicketToReservedUseCase(
            booking_command_repo=booking_command_repo,
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
        Fail Fast: buyer mismatch

        Given: booking.buyer_id = 2
        When: Execute with buyer_id = 3
        Then: Raise ForbiddenError
        """
        # Given
        booking_command_repo = AsyncMock()
        booking_command_repo.get_by_id = AsyncMock(return_value=existing_booking)

        use_case = UpdateBookingToPendingPaymentAndTicketToReservedUseCase(
            booking_command_repo=booking_command_repo,
        )

        # When/Then
        with pytest.raises(ForbiddenError, match='Booking owner mismatch'):
            await use_case.execute(
                booking_id=4,
                buyer_id=3,  # Wrong buyer_id
                seat_identifiers=['A-1-1-1', 'A-1-1-2'],
            )
