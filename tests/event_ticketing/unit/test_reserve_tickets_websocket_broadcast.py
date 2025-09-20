#!/usr/bin/env python3
"""
ReserveTicketsUseCase WebSocket 廣播功能單元測試
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.event_ticketing.use_case.reserve_tickets_use_case import ReserveTicketsUseCase


class TestReserveTicketsWebSocketBroadcast:
    """ReserveTicketsUseCase WebSocket 廣播功能單元測試"""

    @pytest.fixture
    def mock_session(self):
        """Mock database session"""
        return AsyncMock()

    @pytest.fixture
    def mock_ticket_repo(self):
        """Mock ticket repository"""
        repo = AsyncMock()
        return repo

    @pytest.fixture
    def use_case(self, mock_session, mock_ticket_repo):
        """Create ReserveTicketsUseCase instance"""
        mock_uow = MagicMock()
        mock_uow.session = mock_session
        mock_uow.ticket_repo = mock_ticket_repo
        return ReserveTicketsUseCase(uow=mock_uow)  # type: ignore

    @pytest.fixture
    def mock_tickets(self):
        """Create mock tickets for testing"""
        ticket1 = MagicMock()
        ticket1.id = 1001
        ticket1.section = 'A'
        ticket1.subsection = 1
        ticket1.row = 1
        ticket1.seat = 1
        ticket1.seat_identifier = 'A-1-1-1'
        ticket1.price = 100
        ticket1.reserve = MagicMock()

        ticket2 = MagicMock()
        ticket2.id = 1002
        ticket2.section = 'A'
        ticket2.subsection = 1
        ticket2.row = 1
        ticket2.seat = 2
        ticket2.seat_identifier = 'A-1-1-2'
        ticket2.price = 100
        ticket2.reserve = MagicMock()

        ticket3 = MagicMock()
        ticket3.id = 1003
        ticket3.section = 'B'
        ticket3.subsection = 2
        ticket3.row = 1
        ticket3.seat = 1
        ticket3.seat_identifier = 'B-2-1-1'
        ticket3.price = 150
        ticket3.reserve = MagicMock()

        return [ticket1, ticket2, ticket3]

    @pytest.fixture
    def mock_remaining_tickets(self):
        """Create mock remaining tickets for count calculation"""
        remaining_ticket1 = MagicMock()
        remaining_ticket1.section = 'A'
        remaining_ticket1.subsection = 1

        remaining_ticket2 = MagicMock()
        remaining_ticket2.section = 'A'
        remaining_ticket2.subsection = 1

        remaining_ticket3 = MagicMock()
        remaining_ticket3.section = 'B'
        remaining_ticket3.subsection = 2

        return [remaining_ticket1, remaining_ticket2, remaining_ticket3]

    @pytest.mark.asyncio
    async def test_broadcast_subsection_specific_events(
        self, use_case, mock_ticket_repo, mock_session, mock_tickets
    ):
        """測試分區特定廣播事件"""
        # Arrange
        event_id = 456
        buyer_id = 1
        ticket_count = 2

        # Setup mock tickets - only first 2 tickets (same subsection)
        tickets_to_reserve = mock_tickets[:2]
        mock_ticket_repo.get_available_tickets_for_event.return_value = tickets_to_reserve

        # Mock remaining ticket counts
        with patch.object(use_case, '_get_remaining_ticket_counts') as mock_remaining_counts:
            mock_remaining_counts.return_value = {'A-1': 5, 'B-2': 3}

            with patch(
                'src.shared.websocket.ticket_websocket_service.ticket_websocket_service'
            ) as mock_ws_service:
                mock_ws_service.broadcast_subsection_event = AsyncMock()
                mock_ws_service.broadcast_ticket_event = AsyncMock()

                # Act
                result = await use_case.reserve_tickets(
                    event_id=event_id, ticket_count=ticket_count, buyer_id=buyer_id
                )

                # Assert
                # Verify ticket reservation
                assert result['reservation_id'] == 1001
                assert result['buyer_id'] == buyer_id
                assert result['event_id'] == event_id
                assert result['ticket_count'] == ticket_count
                assert len(result['tickets']) == 2

                # Verify subsection-specific broadcast was called
                mock_ws_service.broadcast_subsection_event.assert_called_once()
                subsection_call = mock_ws_service.broadcast_subsection_event.call_args

                assert subsection_call.kwargs['event_id'] == event_id
                assert subsection_call.kwargs['section'] == 'A'
                assert subsection_call.kwargs['subsection'] == 1
                assert subsection_call.kwargs['event_type'] == 'tickets_reserved'

                # Check subsection broadcast data
                subsection_data = subsection_call.kwargs['data']
                assert subsection_data['reservation_count'] == 2
                assert subsection_data['remaining_count'] == 5
                assert len(subsection_data['tickets']) == 2
                assert subsection_data['buyer_id'] == buyer_id

                # Verify general broadcast was called
                mock_ws_service.broadcast_ticket_event.assert_called_once()
                general_call = mock_ws_service.broadcast_ticket_event.call_args

                assert general_call.kwargs['event_id'] == event_id
                assert general_call.kwargs['event_type'] == 'reservation_summary'

                # Check general broadcast data
                general_data = general_call.kwargs['ticket_data']
                assert general_data['total_reserved'] == 2
                assert 'A-1' in general_data['affected_subsections']
                assert general_data['remaining_counts_by_subsection'] == {'A-1': 5, 'B-2': 3}

    @pytest.mark.asyncio
    async def test_broadcast_multiple_subsections(
        self, use_case, mock_ticket_repo, mock_session, mock_tickets
    ):
        """測試跨多個分區的廣播事件"""
        # Arrange
        event_id = 456
        buyer_id = 1
        ticket_count = 3

        # Setup mock tickets - all 3 tickets (different subsections)
        mock_ticket_repo.get_available_tickets_for_event.return_value = mock_tickets

        # Mock remaining ticket counts
        with patch.object(use_case, '_get_remaining_ticket_counts') as mock_remaining_counts:
            mock_remaining_counts.return_value = {'A-1': 3, 'B-2': 2}

            with patch(
                'src.shared.websocket.ticket_websocket_service.ticket_websocket_service'
            ) as mock_ws_service:
                mock_ws_service.broadcast_subsection_event = AsyncMock()
                mock_ws_service.broadcast_ticket_event = AsyncMock()

                # Act
                result = await use_case.reserve_tickets(
                    event_id=event_id, ticket_count=ticket_count, buyer_id=buyer_id
                )

                # Assert
                assert result['ticket_count'] == 3
                assert len(result['tickets']) == 3

                # Verify subsection-specific broadcasts were called twice (for A-1 and B-2)
                assert mock_ws_service.broadcast_subsection_event.call_count == 2

                # Check both subsection calls
                subsection_calls = mock_ws_service.broadcast_subsection_event.call_args_list

                # First subsection (A-1) - should have 2 tickets
                call_a1 = next(call for call in subsection_calls if call.kwargs['section'] == 'A')
                assert call_a1.kwargs['subsection'] == 1
                assert call_a1.kwargs['data']['reservation_count'] == 2
                assert call_a1.kwargs['data']['remaining_count'] == 3

                # Second subsection (B-2) - should have 1 ticket
                call_b2 = next(call for call in subsection_calls if call.kwargs['section'] == 'B')
                assert call_b2.kwargs['subsection'] == 2
                assert call_b2.kwargs['data']['reservation_count'] == 1
                assert call_b2.kwargs['data']['remaining_count'] == 2

                # Verify general broadcast
                mock_ws_service.broadcast_ticket_event.assert_called_once()
                general_call = mock_ws_service.broadcast_ticket_event.call_args
                general_data = general_call.kwargs['ticket_data']

                assert general_data['total_reserved'] == 3
                assert set(general_data['affected_subsections']) == {'A-1', 'B-2'}

    @pytest.mark.asyncio
    async def test_remaining_ticket_count_calculation(
        self, use_case, mock_ticket_repo, mock_remaining_tickets
    ):
        """測試剩餘票數計算功能"""
        # Arrange
        event_id = 456

        # Setup mock remaining tickets
        mock_ticket_repo.get_available_tickets_for_event.return_value = mock_remaining_tickets

        # Act
        remaining_counts = await use_case._get_remaining_ticket_counts(event_id=event_id)

        # Assert
        # Verify the method was called with correct parameters
        mock_ticket_repo.get_available_tickets_for_event.assert_called_once_with(
            event_id=event_id, limit=None
        )

        # Verify counts are correctly calculated
        expected_counts = {
            'A-1': 2,  # 2 tickets in A-1
            'B-2': 1,  # 1 ticket in B-2
        }
        assert remaining_counts == expected_counts

    @pytest.mark.asyncio
    async def test_broadcast_with_websocket_failure(
        self, use_case, mock_ticket_repo, mock_session, mock_tickets
    ):
        """測試 WebSocket 廣播失敗時的錯誤處理"""
        # Arrange
        event_id = 456
        buyer_id = 1
        ticket_count = 2

        tickets_to_reserve = mock_tickets[:2]
        mock_ticket_repo.get_available_tickets_for_event.return_value = tickets_to_reserve

        # Mock remaining ticket counts
        with patch.object(use_case, '_get_remaining_ticket_counts') as mock_remaining_counts:
            mock_remaining_counts.return_value = {'A-1': 5}

            with patch(
                'src.shared.websocket.ticket_websocket_service.ticket_websocket_service'
            ) as mock_ws_service:
                # Make WebSocket broadcast fail
                mock_ws_service.broadcast_subsection_event.side_effect = Exception(
                    'WebSocket connection failed'
                )

                # Act - should not raise exception even if WebSocket fails
                result = await use_case.reserve_tickets(
                    event_id=event_id, ticket_count=ticket_count, buyer_id=buyer_id
                )

                # Assert
                # Reservation should still succeed despite WebSocket failure
                assert result['reservation_id'] == 1001
                assert result['buyer_id'] == buyer_id
                assert result['ticket_count'] == ticket_count

                # Verify WebSocket broadcast was attempted
                mock_ws_service.broadcast_subsection_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_remaining_ticket_counts_with_error(self, use_case, mock_ticket_repo):
        """測試剩餘票數計算遇到錯誤時的處理"""
        # Arrange
        event_id = 456

        # Make ticket repo fail
        mock_ticket_repo.get_available_tickets_for_event.side_effect = Exception('Database error')

        # Act
        remaining_counts = await use_case._get_remaining_ticket_counts(event_id=event_id)

        # Assert
        # Should return empty dict when error occurs
        assert remaining_counts == {}

        # Verify the method was called
        mock_ticket_repo.get_available_tickets_for_event.assert_called_once_with(
            event_id=event_id, limit=None
        )
