#!/usr/bin/env python3
"""
TicketingEventHandler 單元測試
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.event_ticketing.infra.ticketing_event_handler import TicketingEventHandler


class TestTicketingEventHandler:
    """TicketingEventHandler 單元測試"""

    @pytest.fixture
    def handler(self):
        """Create TicketingEventHandler instance"""
        return TicketingEventHandler()

    @pytest.fixture
    def mock_reserve_use_case(self):
        """Mock ReserveTicketsUseCase"""
        use_case = AsyncMock()
        return use_case

    @pytest.fixture
    def valid_booking_request_event(self):
        """Create a valid booking request event"""
        return {
            'event_type': 'BookingRequested',
            'aggregate_id': 1,
            'data': {
                'request_id': 'test-request-123',
                'buyer_id': 1,
                'event_id': 456,
                'ticket_count': 2,
            },
        }

    @pytest.fixture
    def successful_reservation_result(self):
        """Create a successful reservation result"""
        return {
            'reservation_id': 789,
            'buyer_id': 1,
            'event_id': 456,
            'ticket_count': 2,
            'status': 'reserved',
            'tickets': [
                {
                    'id': 1001,
                    'seat_identifier': 'A-1-1-1',
                    'price': 100,
                    'section': 'A',
                    'subsection': 1,
                },
                {
                    'id': 1002,
                    'seat_identifier': 'A-1-1-2',
                    'price': 100,
                    'section': 'A',
                    'subsection': 1,
                },
            ],
        }

    @pytest.mark.asyncio
    async def test_can_handle_booking_created(self, handler):
        """測試能否處理 BookingCreated 事件"""
        # Act
        result = await handler.can_handle('BookingCreated')

        # Assert
        assert result is True

    @pytest.mark.asyncio
    async def test_can_handle_unknown_event(self, handler):
        """測試不能處理未知事件"""
        # Act
        result = await handler.can_handle('UnknownEvent')

        # Assert
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_booking_created_success(
        self, handler, valid_booking_request_event, successful_reservation_result
    ):
        """測試成功處理 BookingCreated 事件"""
        # Arrange
        booking_created_event = {
            'event_type': 'BookingCreated',
            'booking_id': 123,
            'buyer_id': 1,
            'event_id': 456,
            'seat_selection_mode': 'best_available',
            'selected_seats': [],
            'numbers_of_seats': 2,
        }

        with patch.object(handler, '_handle_booking_created') as mock_handle:
            mock_handle.return_value = None

            # Act
            await handler.handle(booking_created_event)

            # Assert
            mock_handle.assert_called_once_with(booking_created_event)

    @pytest.mark.asyncio
    async def test_handle_unknown_event_type(self, handler):
        """測試處理未知事件類型"""
        # Arrange
        unknown_event = {'event_type': 'UnknownEvent', 'data': {'test': 'value'}}

        # Act - should not raise exception
        await handler.handle(unknown_event)

        # Assert - No exception raised (handled gracefully)
