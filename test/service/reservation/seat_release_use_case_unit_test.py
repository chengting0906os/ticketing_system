"""
Unit tests for SeatReleaseUseCase

Tests:
- Execution order (Kvrocks -> PostgreSQL -> Pub/Sub -> SSE)
- Successful release of all seats
- Partial release (some seats fail)
- Complete failure handling
"""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.service.reservation.app.command.seat_release_use_case import SeatReleaseUseCase
from src.service.reservation.app.dto import ReleaseSeatsBatchRequest


class TestReleaseSeatExecutionOrder:
    """Test that release_seats executes steps in correct order."""

    @pytest.fixture
    def mock_seat_state_handler(self) -> AsyncMock:
        handler = AsyncMock()
        handler.release_seats = AsyncMock(
            return_value={
                '1-1': True,
                '1-2': True,
            }
        )
        return handler

    @pytest.fixture
    def mock_booking_command_repo(self) -> AsyncMock:
        repo = AsyncMock()
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
        return ReleaseSeatsBatchRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            seat_positions=['1-1', '1-2'],
            event_id=1,
            section='A',
            subsection=1,
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
        Test execution order on success path:
        1. Release seats in Kvrocks
        2. Update PostgreSQL (booking → CANCELLED, tickets → AVAILABLE)
        3. Schedule stats broadcast via Redis Pub/Sub
        4. Publish SSE for booking update

        PostgreSQL write MUST happen AFTER Kvrocks release.
        """
        # Arrange
        call_order: list[str] = []

        async def track_kvrocks(*args: Any, **kwargs: Any) -> dict[str, bool]:
            call_order.append('kvrocks_release')
            return {'1-1': True, '1-2': True}

        async def track_postgres(*args: Any, **kwargs: Any) -> None:
            call_order.append('postgres_update')

        async def track_schedule_broadcast(*args: Any, **kwargs: Any) -> None:
            call_order.append('schedule_stats_broadcast')

        async def track_sse(*args: Any, **kwargs: Any) -> None:
            call_order.append('sse_publish')

        mock_seat_state_handler.release_seats = track_kvrocks
        mock_booking_command_repo.update_status_to_cancelled_and_release_tickets = track_postgres
        mock_pubsub_handler.schedule_stats_broadcast = track_schedule_broadcast
        mock_pubsub_handler.publish_booking_update = track_sse

        # Act
        result = await use_case.execute_batch(valid_request)

        # Assert
        assert result.successful_seats == ['1-1', '1-2']
        assert result.failed_seats == []
        assert result.total_released == 2
        assert call_order == [
            'kvrocks_release',
            'postgres_update',
            'schedule_stats_broadcast',
            'sse_publish',
        ], f'Expected order: kvrocks -> postgres -> schedule_broadcast -> sse, got: {call_order}'

    @pytest.mark.asyncio
    async def test_postgres_update_happens_after_kvrocks_release(
        self,
        use_case: SeatReleaseUseCase,
        mock_seat_state_handler: AsyncMock,
        mock_booking_command_repo: AsyncMock,
        mock_pubsub_handler: AsyncMock,
        valid_request: ReleaseSeatsBatchRequest,
    ) -> None:
        """
        Critical invariant: Kvrocks release MUST complete before PostgreSQL update.
        This ensures seats are released before updating booking status.
        """
        kvrocks_called = False
        postgres_called_before_kvrocks = False

        async def track_kvrocks(*args: Any, **kwargs: Any) -> dict[str, bool]:
            nonlocal kvrocks_called
            kvrocks_called = True
            return {'1-1': True, '1-2': True}

        async def track_postgres(*args: Any, **kwargs: Any) -> None:
            nonlocal postgres_called_before_kvrocks
            if not kvrocks_called:
                postgres_called_before_kvrocks = True

        mock_seat_state_handler.release_seats = track_kvrocks
        mock_booking_command_repo.update_status_to_cancelled_and_release_tickets = track_postgres

        # Act
        await use_case.execute_batch(valid_request)

        # Assert
        assert kvrocks_called, 'Kvrocks release should have been called'
        assert not postgres_called_before_kvrocks, (
            'PostgreSQL update was called before Kvrocks release - this violates the invariant!'
        )


class TestReleaseSeatAtomicFailure:
    """Test atomic failure scenarios - if any seat fails, all fail."""

    @pytest.fixture
    def mock_seat_state_handler(self) -> AsyncMock:
        handler = AsyncMock()
        # Atomic operation: if any seat fails, all results are False
        handler.release_seats = AsyncMock(
            return_value={
                '1-1': False,
                '1-2': False,
            }
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
    async def test_atomic_failure_marks_all_seats_failed(
        self,
        use_case: SeatReleaseUseCase,
    ) -> None:
        """Test that atomic failure correctly reports all seats as failed."""
        request = ReleaseSeatsBatchRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            seat_positions=['1-1', '1-2'],
            event_id=1,
            section='A',
            subsection=1,
        )

        result = await use_case.execute_batch(request)

        # Atomic: all seats fail together
        assert result.successful_seats == []
        assert result.failed_seats == ['1-1', '1-2']
        assert result.total_released == 0
        assert '1-1' in result.error_messages
        assert '1-2' in result.error_messages


class TestReleaseSeatFailure:
    """Test failure scenarios."""

    @pytest.fixture
    def mock_seat_state_handler(self) -> AsyncMock:
        handler = AsyncMock()
        handler.release_seats = AsyncMock(side_effect=Exception('Kvrocks connection error'))
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
    async def test_kvrocks_error_marks_all_seats_failed(
        self,
        use_case: SeatReleaseUseCase,
    ) -> None:
        """Test that Kvrocks error marks all seats as failed."""
        request = ReleaseSeatsBatchRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            seat_positions=['1-1', '1-2'],
            event_id=1,
            section='A',
            subsection=1,
        )

        result = await use_case.execute_batch(request)

        assert result.successful_seats == []
        assert result.failed_seats == ['1-1', '1-2']
        assert result.total_released == 0
        assert '1-1' in result.error_messages
        assert '1-2' in result.error_messages


class TestReleaseSeatPostgresFailure:
    """Test PostgreSQL failure scenarios - should not fail the entire operation."""

    @pytest.fixture
    def mock_seat_state_handler(self) -> AsyncMock:
        handler = AsyncMock()
        handler.release_seats = AsyncMock(return_value={'1-1': True, '1-2': True})
        return handler

    @pytest.fixture
    def mock_booking_command_repo(self) -> AsyncMock:
        repo = AsyncMock()
        # PostgreSQL update fails
        repo.update_status_to_cancelled_and_release_tickets = AsyncMock(
            side_effect=Exception('PostgreSQL connection error')
        )
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
    async def test_postgres_failure_does_not_fail_operation(
        self,
        use_case: SeatReleaseUseCase,
        mock_pubsub_handler: AsyncMock,
    ) -> None:
        """
        Test that PostgreSQL failure does not fail the entire operation.
        Kvrocks release is the primary operation; DB update can be retried.
        """
        request = ReleaseSeatsBatchRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            seat_positions=['1-1', '1-2'],
            event_id=1,
            section='A',
            subsection=1,
        )

        result = await use_case.execute_batch(request)

        # Kvrocks release should still succeed
        assert result.successful_seats == ['1-1', '1-2']
        assert result.failed_seats == []
        assert result.total_released == 2

        # SSE should still be published
        mock_pubsub_handler.schedule_stats_broadcast.assert_called_once()
        mock_pubsub_handler.publish_booking_update.assert_called_once()


class TestReleaseSeatSSEPublish:
    """Test SSE publishing with correct data."""

    @pytest.fixture
    def mock_seat_state_handler(self) -> AsyncMock:
        handler = AsyncMock()
        handler.release_seats = AsyncMock(return_value={'1-1': True})
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
    async def test_sse_publish_contains_correct_data(
        self,
        use_case: SeatReleaseUseCase,
        mock_pubsub_handler: AsyncMock,
    ) -> None:
        """Test that SSE publish contains correct booking update data."""
        request = ReleaseSeatsBatchRequest(
            booking_id='test-booking-id',
            buyer_id=42,
            seat_positions=['1-1'],
            event_id=99,
            section='A',
            subsection=1,
        )

        await use_case.execute_batch(request)

        mock_pubsub_handler.publish_booking_update.assert_called_once_with(
            user_id=42,
            event_id=99,
            event_data={
                'event_type': 'booking_updated',
                'event_id': 99,
                'booking_id': 'test-booking-id',
                'status': 'CANCELLED',
                'tickets': [],
            },
        )
