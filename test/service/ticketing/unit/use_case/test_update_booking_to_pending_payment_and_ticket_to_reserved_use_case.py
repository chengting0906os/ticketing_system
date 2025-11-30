from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from uuid_utils import UUID

from src.service.ticketing.app.command.update_booking_status_to_pending_payment_and_ticket_to_reserved_use_case import (
    UpdateBookingToPendingPaymentAndTicketToReservedUseCase,
)
from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus
from src.service.ticketing.domain.enum.ticket_status import TicketStatus
from src.service.ticketing.domain.value_object.ticket_ref import TicketRef


@pytest.mark.unit
class TestUpdateBookingToPendingPaymentAndTicketToReserved:
    """Test updating booking to PENDING_PAYMENT with RESERVED tickets"""

    @pytest.fixture
    def booking_id(self) -> UUID:
        """Test booking ID"""
        return UUID('00000000-0000-0000-0000-000000000001')

    @pytest.fixture
    def created_booking(self, booking_id: UUID) -> Booking:
        """Newly created booking entity"""
        return Booking(
            id=booking_id,
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
            updated_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def reserved_tickets(self) -> list[TicketRef]:
        """Two reserved tickets"""
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
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
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
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
        ]

    @pytest.mark.asyncio
    async def test_success_creates_booking_and_tickets(
        self, booking_id: UUID, created_booking: Booking, reserved_tickets: list[TicketRef]
    ) -> None:
        # Given: Mock repository returns dict with booking and tickets
        booking_command_repo: Mock = AsyncMock()
        booking_command_repo.create_booking_with_tickets_directly = AsyncMock(
            return_value={
                'booking': created_booking,
                'tickets': reserved_tickets,
            }
        )

        event_broadcaster: Mock = AsyncMock()

        use_case = UpdateBookingToPendingPaymentAndTicketToReservedUseCase(
            booking_command_repo=booking_command_repo,
            event_broadcaster=event_broadcaster,
        )

        # When: Execute with seat format 'A-1-1-1', 'A-1-1-2'
        result = await use_case.execute(
            booking_id=booking_id,
            buyer_id=2,
            event_id=1,
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['A-1-1-1', 'A-1-1-2'],  # section-subsection-row-seat format
            total_price=3000,
        )

        # Then: Repository called with converted format '1-1', '1-2'
        booking_command_repo.create_booking_with_tickets_directly.assert_called_once_with(
            booking_id=booking_id,
            buyer_id=2,
            event_id=1,
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['1-1', '1-2'],  # Converted to row-seat format
            total_price=3000,
        )

        # Then: Returns booking entity
        assert result.id == booking_id
        assert result.status == BookingStatus.PENDING_PAYMENT
        assert result.total_price == 3000

        # Then: SSE broadcast called with ticket data
        event_broadcaster.broadcast.assert_called_once()
        call_args = event_broadcaster.broadcast.call_args
        assert call_args.kwargs['booking_id'] == booking_id
        event_data = call_args.kwargs['event_data']
        assert event_data['status'] == 'pending_payment'
        assert event_data['total_price'] == 3000
        assert len(event_data['tickets']) == 2
        assert event_data['tickets'][0]['id'] == 101
        assert event_data['tickets'][0]['status'] == 'reserved'
        assert event_data['tickets'][0]['seat_identifier'] == 'A-1-1-1'

    @pytest.mark.asyncio
    async def test_sse_broadcast_failure_does_not_fail_use_case(
        self, booking_id: UUID, created_booking: Booking, reserved_tickets: list[TicketRef]
    ) -> None:
        # Given: Repository succeeds but broadcaster fails
        booking_command_repo: Mock = AsyncMock()
        booking_command_repo.create_booking_with_tickets_directly = AsyncMock(
            return_value={
                'booking': created_booking,
                'tickets': reserved_tickets,
            }
        )

        event_broadcaster: Mock = AsyncMock()
        event_broadcaster.broadcast = AsyncMock(side_effect=Exception('SSE connection lost'))

        use_case = UpdateBookingToPendingPaymentAndTicketToReservedUseCase(
            booking_command_repo=booking_command_repo,
            event_broadcaster=event_broadcaster,
        )

        # When: Execute (SSE will fail)
        result = await use_case.execute(
            booking_id=booking_id,
            buyer_id=2,
            event_id=1,
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['A-1-1-1', 'A-1-1-2'],
            total_price=3000,
        )

        # Then: Use case still succeeds
        assert result.id == booking_id
        assert result.status == BookingStatus.PENDING_PAYMENT

        # Then: Repository was called
        booking_command_repo.create_booking_with_tickets_directly.assert_called_once()
