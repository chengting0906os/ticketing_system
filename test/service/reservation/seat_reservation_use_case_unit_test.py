"""
Unit tests for SeatReservationUseCase

Tests:
- Execution order (new 6-step flow)
- Manual mode validation
- Best available mode validation
- Quantity limits
- Failure handling
"""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.service.reservation.app.command.seat_reservation_use_case import SeatReservationUseCase
from src.service.reservation.app.dto import ReservationRequest
from src.service.shared_kernel.domain.value_object.subsection_config import SubsectionConfig


class TestReserveSeatsExecutionOrder:
    """Test that reserve_seats executes steps in correct order (new 6-step flow)."""

    @pytest.fixture
    def mock_seat_state_handler(self) -> AsyncMock:
        handler = AsyncMock()
        # New split methods for 6-step flow
        handler.find_seats = AsyncMock(
            return_value={
                'success': True,
                'seats_to_reserve': [(1, 1, 0, '1-1'), (1, 2, 1, '1-2')],
                'total_price': 2000,
            }
        )
        handler.verify_seats = AsyncMock(
            return_value={
                'success': True,
                'seats_to_reserve': [(1, 1, 0, '1-1')],
                'total_price': 1000,
            }
        )
        handler.update_seat_map = AsyncMock(
            return_value={
                'success': True,
                'reserved_seats': ['1-1', '1-2'],
                'subsection_stats': {},
                'event_stats': {},
            }
        )
        return handler

    @pytest.fixture
    def mock_booking_command_repo(self) -> AsyncMock:
        repo = AsyncMock()
        repo.get_by_id = AsyncMock(return_value=None)  # No existing booking
        repo.create_booking_and_update_tickets_to_reserved = AsyncMock(
            return_value={'tickets': [{'id': 1}]}
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
    ) -> SeatReservationUseCase:
        return SeatReservationUseCase(
            seat_state_handler=mock_seat_state_handler,
            booking_command_repo=mock_booking_command_repo,
            pubsub_handler=mock_pubsub_handler,
        )

    @pytest.fixture
    def valid_request(self) -> ReservationRequest:
        return ReservationRequest(
            booking_id='test-booking-id',
            buyer_id=1,
            event_id=1,
            selection_mode='best_available',
            section_filter='A',
            subsection_filter=1,
            quantity=2,
            config=SubsectionConfig(rows=10, cols=10, price=1000),
        )

    @pytest.mark.asyncio
    async def test_success_path_executes_in_correct_order(
        self,
        use_case: SeatReservationUseCase,
        mock_seat_state_handler: AsyncMock,
        mock_booking_command_repo: AsyncMock,
        mock_pubsub_handler: AsyncMock,
        valid_request: ReservationRequest,
    ) -> None:
        """
        Test execution order on success path (new 6-step flow):
        1. Validate Request (done in use case)
        2. Idempotency Check (PostgreSQL get_by_id)
        3. Find seats (Lua - find_seats)
        4. PostgreSQL write
        5. Update seat map (Pipeline - update_seat_map)
        6. SSE broadcast

        PostgreSQL write MUST happen BEFORE Kvrocks update.
        """
        # Arrange
        call_order: list[str] = []

        async def track_idempotency(*args: Any, **kwargs: Any) -> None:
            call_order.append('idempotency_check')
            return None

        async def track_find_seats(*args: Any, **kwargs: Any) -> dict[str, Any]:
            call_order.append('lua_find_seats')
            return {
                'success': True,
                'seats_to_reserve': [(1, 1, 0, '1-1'), (1, 2, 1, '1-2')],
                'total_price': 2000,
            }

        async def track_postgres(*args: Any, **kwargs: Any) -> dict[str, Any]:
            call_order.append('postgres_write')
            return {'tickets': [{'id': 1}]}

        async def track_update_seat_map(*args: Any, **kwargs: Any) -> dict[str, Any]:
            call_order.append('kvrocks_update_seat_map')
            return {'success': True, 'reserved_seats': ['1-1', '1-2']}

        async def track_schedule_broadcast(*args: Any, **kwargs: Any) -> None:
            call_order.append('schedule_stats_broadcast')

        async def track_sse(*args: Any, **kwargs: Any) -> None:
            call_order.append('sse_publish')

        mock_booking_command_repo.get_by_id = track_idempotency
        mock_seat_state_handler.find_seats = track_find_seats
        mock_booking_command_repo.create_booking_and_update_tickets_to_reserved = track_postgres
        mock_seat_state_handler.update_seat_map = track_update_seat_map
        mock_pubsub_handler.schedule_stats_broadcast = track_schedule_broadcast
        mock_pubsub_handler.publish_booking_update = track_sse

        # Act
        result = await use_case.reserve_seats(valid_request)

        # Assert
        assert result.success is True
        assert call_order == [
            'idempotency_check',
            'lua_find_seats',
            'postgres_write',
            'kvrocks_update_seat_map',
            'schedule_stats_broadcast',
            'sse_publish',
        ], f'Expected 6-step flow order, got: {call_order}'

    @pytest.mark.asyncio
    async def test_postgres_write_happens_before_broadcast(
        self,
        use_case: SeatReservationUseCase,
        mock_seat_state_handler: AsyncMock,
        mock_booking_command_repo: AsyncMock,
        mock_pubsub_handler: AsyncMock,
        valid_request: ReservationRequest,
    ) -> None:
        """
        Critical invariant: PostgreSQL write MUST complete before broadcasting.
        This ensures data is persisted before notifying clients.
        """
        postgres_called = False
        broadcast_when_postgres_not_called = False

        async def track_postgres(*args: Any, **kwargs: Any) -> dict[str, Any]:
            nonlocal postgres_called
            postgres_called = True
            return {'tickets': [{'id': 1}]}

        async def track_schedule_broadcast(*args: Any, **kwargs: Any) -> None:
            nonlocal broadcast_when_postgres_not_called
            if not postgres_called:
                broadcast_when_postgres_not_called = True

        # Setup new flow mocks
        mock_booking_command_repo.get_by_id = AsyncMock(return_value=None)
        mock_seat_state_handler.find_seats = AsyncMock(
            return_value={
                'success': True,
                'seats_to_reserve': [(1, 1, 0, '1-1')],
                'total_price': 1000,
            }
        )
        mock_booking_command_repo.create_booking_and_update_tickets_to_reserved = track_postgres
        mock_seat_state_handler.update_seat_map = AsyncMock(
            return_value={'success': True, 'reserved_seats': ['1-1']}
        )
        mock_pubsub_handler.schedule_stats_broadcast = track_schedule_broadcast

        # Act
        await use_case.reserve_seats(valid_request)

        # Assert
        assert postgres_called, 'PostgreSQL write should have been called'
        assert not broadcast_when_postgres_not_called, (
            'schedule_stats_broadcast was called before PostgreSQL write - this violates the invariant!'
        )
