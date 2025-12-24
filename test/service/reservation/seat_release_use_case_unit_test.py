"""
Unit tests for SeatReleaseUseCase

Tests PostgreSQL-first flow:
1. Idempotency check (PostgreSQL get_by_id)
2. PostgreSQL write (booking → CANCELLED, tickets → AVAILABLE)
3. Fetch config from Kvrocks
4. Update seat map in Kvrocks
5. SSE broadcast
"""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.service.reservation.app.command.seat_release_use_case import SeatReleaseUseCase
from src.service.reservation.app.dto import ReleaseSeatsBatchRequest
from src.service.shared_kernel.domain.value_object import BookingStatus


def _make_mock_booking(
    status: BookingStatus = BookingStatus.PENDING_PAYMENT,
    buyer_id: int = 1,
    event_id: int = 1,
    section: str = 'A',
    subsection: int = 1,
) -> AsyncMock:
    """Create a mock booking with given attributes."""
    booking = AsyncMock()
    booking.id = 'test-booking-id'
    booking.status = status
    booking.buyer_id = buyer_id
    booking.event_id = event_id
    booking.section = section
    booking.subsection = subsection
    booking.seat_positions = ['1-1', '1-2']
    return booking


class TestReleaseSeatExecutionOrder:
    """Test that release_seats executes steps in correct order (PostgreSQL-first)."""

    @pytest.fixture
    def mock_seat_state_handler(self) -> AsyncMock:
        handler = AsyncMock()
        handler.fetch_release_config = AsyncMock(return_value={'success': True, 'cols': 10})
        handler.update_seat_map_release = AsyncMock(
            return_value={'success': True, 'released_seats': ['1-1', '1-2']}
        )
        return handler

    @pytest.fixture
    def mock_booking_command_repo(self) -> AsyncMock:
        repo = AsyncMock()
        repo.get_by_id = AsyncMock(return_value=_make_mock_booking(BookingStatus.PENDING_PAYMENT))
        repo.update_status_to_cancelled_and_release_tickets = AsyncMock(return_value=None)
        return repo

    @pytest.fixture
    def mock_pubsub_handler(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def use_case(
        self,
        mock_seat_state_handler: AsyncMock,
        mock_booking_command_repo: AsyncMock,
        mock_pubsub_handler: AsyncMock,
    ) -> SeatReleaseUseCase:
        return SeatReleaseUseCase(
            seat_state_handler=mock_seat_state_handler,
            booking_command_repo=mock_booking_command_repo,
            pubsub_handler=mock_pubsub_handler,
        )

    @pytest.fixture
    def valid_request(self) -> ReleaseSeatsBatchRequest:
        """Minimal request - use case fetches details from DB."""
        return ReleaseSeatsBatchRequest(
            booking_id='test-booking-id',
            event_id=1,
        )

    @pytest.mark.asyncio
    async def test_success_path_executes_in_correct_order(
        self,
        use_case: SeatReleaseUseCase,
        mock_seat_state_handler: AsyncMock,
        mock_booking_command_repo: AsyncMock,
        mock_pubsub_handler: AsyncMock,
        valid_request: ReleaseSeatsBatchRequest,
    ) -> None:
        """
        Test execution order on success path (PostgreSQL-first flow):
        1. Idempotency check (PostgreSQL get_by_id)
        2. PostgreSQL write (booking → CANCELLED, tickets → AVAILABLE)
        3. Fetch config from Kvrocks
        4. Update seat map in Kvrocks
        5. Schedule stats broadcast via Redis Pub/Sub
        6. Publish SSE for booking update
        """
        call_order: list[str] = []

        async def track_get_by_id(*args: Any, **kwargs: Any) -> AsyncMock:
            call_order.append('postgres_get_by_id')
            return _make_mock_booking(BookingStatus.PENDING_PAYMENT)

        async def track_postgres_update(*args: Any, **kwargs: Any) -> None:
            call_order.append('postgres_update')

        async def track_fetch_config(*args: Any, **kwargs: Any) -> dict:
            call_order.append('kvrocks_fetch_config')
            return {'success': True, 'cols': 10}

        async def track_kvrocks_update(*args: Any, **kwargs: Any) -> dict:
            call_order.append('kvrocks_update')
            return {'success': True, 'released_seats': ['1-1', '1-2']}

        async def track_schedule_broadcast(*args: Any, **kwargs: Any) -> None:
            call_order.append('schedule_stats_broadcast')

        async def track_sse(*args: Any, **kwargs: Any) -> None:
            call_order.append('sse_publish')

        mock_booking_command_repo.get_by_id = track_get_by_id
        mock_booking_command_repo.update_status_to_cancelled_and_release_tickets = (
            track_postgres_update
        )
        mock_seat_state_handler.fetch_release_config = track_fetch_config
        mock_seat_state_handler.update_seat_map_release = track_kvrocks_update
        mock_pubsub_handler.schedule_stats_broadcast = track_schedule_broadcast
        mock_pubsub_handler.publish_booking_update = track_sse

        result = await use_case.execute_batch(valid_request)

        assert result.successful_seats == ['1-1', '1-2']
        assert result.failed_seats == []
        assert result.total_released == 2
        assert call_order == [
            'postgres_get_by_id',
            'postgres_update',
            'kvrocks_fetch_config',
            'kvrocks_update',
            'schedule_stats_broadcast',
            'sse_publish',
        ], f'Expected PostgreSQL-first order, got: {call_order}'

    @pytest.mark.asyncio
    async def test_postgres_write_happens_before_kvrocks_update(
        self,
        use_case: SeatReleaseUseCase,
        mock_seat_state_handler: AsyncMock,
        mock_booking_command_repo: AsyncMock,
        mock_pubsub_handler: AsyncMock,
        valid_request: ReleaseSeatsBatchRequest,
    ) -> None:
        """
        Critical invariant: PostgreSQL write MUST complete before Kvrocks update.
        PostgreSQL is source of truth; Kvrocks update can be retried if it fails.
        """
        postgres_called = False
        kvrocks_called_before_postgres = False

        async def track_postgres(*args: Any, **kwargs: Any) -> None:
            nonlocal postgres_called
            postgres_called = True

        async def track_kvrocks(*args: Any, **kwargs: Any) -> dict:
            nonlocal kvrocks_called_before_postgres
            if not postgres_called:
                kvrocks_called_before_postgres = True
            return {'success': True, 'released_seats': ['1-1', '1-2']}

        mock_booking_command_repo.update_status_to_cancelled_and_release_tickets = track_postgres
        mock_seat_state_handler.update_seat_map_release = track_kvrocks

        await use_case.execute_batch(valid_request)

        assert postgres_called, 'PostgreSQL update should have been called'
        assert not kvrocks_called_before_postgres, (
            'Kvrocks update was called before PostgreSQL write - this violates the invariant!'
        )


class TestReleaseSeatIdempotency:
    """Test idempotency scenarios."""

    @pytest.fixture
    def mock_seat_state_handler(self) -> AsyncMock:
        handler = AsyncMock()
        handler.fetch_release_config = AsyncMock(return_value={'success': True, 'cols': 10})
        handler.update_seat_map_release = AsyncMock(
            return_value={'success': True, 'released_seats': ['1-1', '1-2']}
        )
        return handler

    @pytest.fixture
    def mock_booking_command_repo(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def mock_pubsub_handler(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def use_case(
        self,
        mock_seat_state_handler: AsyncMock,
        mock_booking_command_repo: AsyncMock,
        mock_pubsub_handler: AsyncMock,
    ) -> SeatReleaseUseCase:
        return SeatReleaseUseCase(
            seat_state_handler=mock_seat_state_handler,
            booking_command_repo=mock_booking_command_repo,
            pubsub_handler=mock_pubsub_handler,
        )

    @pytest.mark.asyncio
    async def test_already_cancelled_booking_skips_postgres_update(
        self,
        use_case: SeatReleaseUseCase,
        mock_booking_command_repo: AsyncMock,
    ) -> None:
        """Test that already cancelled bookings complete remaining steps without PostgreSQL write."""
        mock_booking_command_repo.get_by_id = AsyncMock(
            return_value=_make_mock_booking(BookingStatus.CANCELLED)
        )

        request = ReleaseSeatsBatchRequest(
            booking_id='test-booking-id',
            event_id=1,
        )

        result = await use_case.execute_batch(request)

        assert result.successful_seats == ['1-1', '1-2']
        mock_booking_command_repo.update_status_to_cancelled_and_release_tickets.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_pending_payment_booking_fails(
        self,
        use_case: SeatReleaseUseCase,
        mock_booking_command_repo: AsyncMock,
    ) -> None:
        """Test that bookings not in PENDING_PAYMENT status return error."""
        mock_booking_command_repo.get_by_id = AsyncMock(
            return_value=_make_mock_booking(BookingStatus.COMPLETED)
        )

        request = ReleaseSeatsBatchRequest(
            booking_id='test-booking-id',
            event_id=1,
        )

        result = await use_case.execute_batch(request)

        assert result.successful_seats == []
        assert result.failed_seats == []  # No seat_positions in request, error at booking level
        assert 'not in PENDING_PAYMENT status' in result.error_messages['booking']


class TestReleaseSeatSSEPublish:
    """Test SSE publishing with correct data."""

    @pytest.fixture
    def mock_seat_state_handler(self) -> AsyncMock:
        handler = AsyncMock()
        handler.fetch_release_config = AsyncMock(return_value={'success': True, 'cols': 10})
        handler.update_seat_map_release = AsyncMock(
            return_value={'success': True, 'released_seats': ['1-1']}
        )
        return handler

    @pytest.fixture
    def mock_booking_command_repo(self) -> AsyncMock:
        repo = AsyncMock()
        # Mock booking with buyer_id=42, event_id=99 for SSE assertions
        repo.get_by_id = AsyncMock(
            return_value=_make_mock_booking(BookingStatus.PENDING_PAYMENT, buyer_id=42, event_id=99)
        )
        repo.update_status_to_cancelled_and_release_tickets = AsyncMock(return_value=None)
        return repo

    @pytest.fixture
    def mock_pubsub_handler(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def use_case(
        self,
        mock_seat_state_handler: AsyncMock,
        mock_booking_command_repo: AsyncMock,
        mock_pubsub_handler: AsyncMock,
    ) -> SeatReleaseUseCase:
        return SeatReleaseUseCase(
            seat_state_handler=mock_seat_state_handler,
            booking_command_repo=mock_booking_command_repo,
            pubsub_handler=mock_pubsub_handler,
        )

    @pytest.mark.asyncio
    async def test_sse_publish_contains_correct_data(
        self,
        use_case: SeatReleaseUseCase,
        mock_pubsub_handler: AsyncMock,
    ) -> None:
        """Test that SSE publish contains correct booking update data (from DB)."""
        request = ReleaseSeatsBatchRequest(
            booking_id='test-booking-id',
            event_id=99,
        )

        await use_case.execute_batch(request)

        # SSE uses booking data from DB (buyer_id=42, event_id=99)
        mock_pubsub_handler.publish_booking_update.assert_called_once_with(
            user_id=42,
            event_id=99,
            event_data={
                'event_type': 'booking_updated',
                'event_id': 99,
                'booking_id': 'test-booking-id',
                'status': BookingStatus.CANCELLED,
                'tickets': [],
            },
        )
