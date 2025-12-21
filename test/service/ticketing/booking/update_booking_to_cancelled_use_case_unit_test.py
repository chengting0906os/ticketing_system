"""
Unit tests for UpdateBookingToCancelledUseCase

Test Focus:
1. Domain validation: Only PROCESSING/PENDING_PAYMENT bookings can be cancelled
2. Event emission: BookingCancelledEvent is sent to trigger seat release in Reservation Service
3. Fail Fast: booking not found, permission denied, invalid status (including already cancelled)

Note: DB update is now handled by Reservation Service after receiving BookingCancelledEvent.
This use case only validates and publishes the event.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from uuid_utils import UUID

from src.platform.exception.exceptions import DomainError, ForbiddenError, NotFoundError
from src.service.ticketing.app.command.update_booking_status_to_cancelled_use_case import (
    UpdateBookingToCancelledUseCase,
)
from src.service.ticketing.domain.entity.booking_entity import Booking, BookingStatus


@pytest.mark.unit
class TestUpdateBookingToCancelled:
    @pytest.fixture
    def pending_payment_booking(self) -> Booking:
        return Booking(
            id=UUID('00000000-0000-0000-0000-00000000000a'),
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
    def mock_booking_repo(self) -> Mock:
        return AsyncMock()

    @pytest.fixture
    def mock_event_publisher(self) -> Mock:
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_successfully_request_cancellation(
        self,
        pending_payment_booking: Booking,
        mock_booking_repo: Mock,
        mock_event_publisher: Mock,
    ) -> None:
        """
        Core test: Successfully request booking cancellation

        Given: Booking with PENDING_PAYMENT status
        When: Buyer executes cancellation
        Then:
          - BookingCancelledEvent is published to Kafka
          - Returns booking with CANCELLED status (pending async update)
          - DB is NOT updated directly (handled by Reservation Service)
        """
        # Arrange
        mock_booking_repo.get_by_id = AsyncMock(return_value=pending_payment_booking)

        use_case = UpdateBookingToCancelledUseCase(
            booking_command_repo=mock_booking_repo,
            event_publisher=mock_event_publisher,
        )

        # Act
        result = await use_case.execute(
            booking_id=UUID('00000000-0000-0000-0000-00000000000a'), buyer_id=2
        )

        # Assert
        assert result.status == BookingStatus.CANCELLED
        assert result.id == UUID('00000000-0000-0000-0000-00000000000a')

        # Verify event was published (not DB update)
        mock_event_publisher.publish_booking_cancelled.assert_called_once()
        call_args = mock_event_publisher.publish_booking_cancelled.call_args
        event = call_args.kwargs['event']
        assert event.booking_id == UUID('00000000-0000-0000-0000-00000000000a')
        assert event.buyer_id == 2
        assert event.event_id == 1
        assert event.seat_positions == ['1-1', '1-2']

        # Verify DB update was NOT called (moved to Reservation Service)
        assert (
            not hasattr(mock_booking_repo, 'update_status_to_cancelled')
            or not mock_booking_repo.update_status_to_cancelled.called
        )

    @pytest.mark.asyncio
    async def test_fail_when_booking_not_found(
        self, mock_booking_repo: Mock, mock_event_publisher: Mock
    ) -> None:
        """
        Fail Fast: Booking does not exist

        Given: Non-existent booking_id
        When: Execute cancellation
        Then: Raises NotFoundError
        """
        # Arrange
        mock_booking_repo.get_by_id = AsyncMock(return_value=None)
        use_case = UpdateBookingToCancelledUseCase(
            booking_command_repo=mock_booking_repo,
            event_publisher=mock_event_publisher,
        )

        # Act & Assert
        with pytest.raises(NotFoundError, match='Booking not found'):
            await use_case.execute(
                booking_id=UUID('00000000-0000-0000-0000-0000000003e7'), buyer_id=2
            )

    @pytest.mark.asyncio
    async def test_fail_when_not_booking_owner(
        self, pending_payment_booking: Booking, mock_booking_repo: Mock, mock_event_publisher: Mock
    ) -> None:
        """
        Fail Fast: Not the booking owner

        Given: Booking with buyer_id=2
        When: buyer_id=3 attempts to cancel
        Then: Raises ForbiddenError
        """
        # Arrange
        mock_booking_repo.get_by_id = AsyncMock(return_value=pending_payment_booking)
        use_case = UpdateBookingToCancelledUseCase(
            booking_command_repo=mock_booking_repo,
            event_publisher=mock_event_publisher,
        )

        # Act & Assert
        with pytest.raises(ForbiddenError, match='Only the buyer can cancel this booking'):
            await use_case.execute(
                booking_id=UUID('00000000-0000-0000-0000-00000000000a'), buyer_id=3
            )  # Different buyer_id

    @pytest.mark.asyncio
    async def test_fail_when_booking_already_completed(
        self, mock_booking_repo: Mock, mock_event_publisher: Mock
    ) -> None:
        """
        Domain validation: Completed bookings cannot be cancelled

        Given: Booking with COMPLETED status
        When: Execute cancellation
        Then: Raises DomainError (returns 400 per spec)
        """
        # Arrange
        completed_booking = Booking(
            id=UUID('00000000-0000-0000-0000-00000000000b'),
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
        mock_booking_repo.get_by_id = AsyncMock(return_value=completed_booking)
        use_case = UpdateBookingToCancelledUseCase(
            booking_command_repo=mock_booking_repo,
            event_publisher=mock_event_publisher,
        )

        # Act & Assert
        with pytest.raises(DomainError, match='Cannot cancel a completed booking'):
            await use_case.execute(
                booking_id=UUID('00000000-0000-0000-0000-00000000000b'), buyer_id=2
            )

    @pytest.mark.asyncio
    async def test_fail_when_booking_already_cancelled(
        self, mock_booking_repo: Mock, mock_event_publisher: Mock
    ) -> None:
        """
        Domain validation: Already cancelled bookings cannot be cancelled again

        Given: Booking with CANCELLED status
        When: Execute cancellation again
        Then: Raises DomainError (returns 400)
        """
        # Arrange
        cancelled_booking = Booking(
            id=UUID('00000000-0000-0000-0000-00000000000c'),
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
        mock_booking_repo.get_by_id = AsyncMock(return_value=cancelled_booking)
        use_case = UpdateBookingToCancelledUseCase(
            booking_command_repo=mock_booking_repo,
            event_publisher=mock_event_publisher,
        )

        # Act & Assert
        with pytest.raises(DomainError, match='Booking is already cancelled'):
            await use_case.execute(
                booking_id=UUID('00000000-0000-0000-0000-00000000000c'), buyer_id=2
            )

    @pytest.mark.asyncio
    async def test_event_contains_seat_positions_from_booking(
        self, pending_payment_booking: Booking, mock_booking_repo: Mock, mock_event_publisher: Mock
    ) -> None:
        """
        Event content validation: seat_positions from booking.seat_positions

        Given: Booking with seat_positions ['1-1', '1-2']
        When: Cancel booking
        Then: Event's seat_positions equals booking.seat_positions
        """
        # Arrange
        mock_booking_repo.get_by_id = AsyncMock(return_value=pending_payment_booking)

        use_case = UpdateBookingToCancelledUseCase(
            booking_command_repo=mock_booking_repo,
            event_publisher=mock_event_publisher,
        )

        # Act
        await use_case.execute(booking_id=UUID('00000000-0000-0000-0000-00000000000a'), buyer_id=2)

        # Assert
        mock_event_publisher.publish_booking_cancelled.assert_called_once()
        event = mock_event_publisher.publish_booking_cancelled.call_args.kwargs['event']
        assert event.seat_positions == ['1-1', '1-2']
