#!/usr/bin/env python3
"""
TicketWebSocketService 廣播功能單元測試
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.shared.websocket.ticket_websocket_service import TicketWebSocketService


class TestTicketWebSocketBroadcastService:
    """TicketWebSocketService 廣播功能單元測試"""

    @pytest.fixture
    def mock_connection_manager(self):
        """Mock WebSocket connection manager"""
        manager = MagicMock()
        manager.broadcast_to_group = AsyncMock()
        manager.broadcast_to_filtered = AsyncMock()
        manager.get_group_size = MagicMock(return_value=5)
        return manager

    @pytest.fixture
    def mock_codec(self):
        """Mock message codec"""
        codec = MagicMock()
        codec.encode_message = MagicMock(return_value=b'encoded_message')
        return codec

    @pytest.fixture
    def websocket_service(self, mock_connection_manager, mock_codec):
        """Create TicketWebSocketService instance with mocked dependencies"""
        service = TicketWebSocketService()
        service.connection_manager = mock_connection_manager
        service.codec = mock_codec
        # Also mock the event_broadcaster's dependencies since that's where the actual operations happen
        service.event_broadcaster.codec = mock_codec  # type: ignore[attr-defined]
        service.event_broadcaster.connection_manager = mock_connection_manager  # type: ignore[attr-defined]
        return service

    @pytest.mark.asyncio
    async def test_broadcast_subsection_event_to_subscribers(
        self, websocket_service, mock_connection_manager, mock_codec
    ):
        """測試分區廣播事件到訂閱用戶"""
        # Arrange
        event_id = 456
        section = 'A'
        subsection = 1
        event_type = 'tickets_reserved'
        data = {
            'event_id': event_id,
            'section': section,
            'subsection': subsection,
            'tickets': [
                {'id': 1001, 'seat_identifier': 'A-1-1-1', 'price': 100, 'status': 'reserved'}
            ],
            'buyer_id': 1,
            'reservation_count': 1,
            'remaining_count': 5,
        }

        # Act
        await websocket_service.broadcast_subsection_event(
            event_id=event_id,
            section=section,
            subsection=subsection,
            event_type=event_type,
            data=data,
        )

        # Assert
        # Verify message encoding
        mock_codec.encode_message.assert_called_once()
        encode_call = mock_codec.encode_message.call_args

        message = encode_call.kwargs['data']
        assert message['type'] == f'subsection_{event_type}'
        assert message['event_id'] == event_id
        assert message['section'] == section
        assert message['subsection'] == subsection
        assert message['subsection_id'] == f'{section}-{subsection}'
        assert message['data'] == data
        assert 'timestamp' in message

        # Verify filtered broadcast
        mock_connection_manager.broadcast_to_filtered.assert_called_once()
        broadcast_call = mock_connection_manager.broadcast_to_filtered.call_args

        assert broadcast_call.kwargs['group_id'] == f'event_{event_id}'  # group_id
        assert broadcast_call.kwargs['data'] == b'encoded_message'  # encoded message

        # Test the filter function
        filter_func = broadcast_call.kwargs['filter_func']

        # User subscribed to specific subsection
        metadata_with_subsection = {'subscribed_sections': {'A-1'}}
        assert filter_func(metadata_with_subsection) is True

        # User subscribed to general section
        metadata_with_section = {'subscribed_sections': {'A'}}
        assert filter_func(metadata_with_section) is True

        # User subscribed to event
        metadata_with_event = {'subscribed_sections': {'event_456'}}
        assert filter_func(metadata_with_event) is True

        # User not subscribed
        metadata_no_subscription = {'subscribed_sections': set()}
        assert filter_func(metadata_no_subscription) is True  # No filter, send to all

        # User subscribed to different section
        metadata_different = {'subscribed_sections': {'B-2'}}
        assert filter_func(metadata_different) is False

    @pytest.mark.asyncio
    async def test_broadcast_ticket_event_with_section_filter(
        self, websocket_service, mock_connection_manager, mock_codec
    ):
        """測試帶分區過濾的票務事件廣播"""
        # Arrange
        event_id = 456
        ticket_data = {
            'id': 1001,
            'seat_identifier': 'A-1-1-1',
            'price': 100,
            'section': 'A',
            'subsection': 1,
        }
        event_type = 'reserved'
        affected_sections = ['A-1', 'B-2']

        # Act
        await websocket_service.broadcast_ticket_event(
            event_id=event_id,
            ticket_data=ticket_data,
            event_type=event_type,
            affected_sections=affected_sections,
        )

        # Assert
        # Verify message encoding
        mock_codec.encode_message.assert_called_once()
        encode_call = mock_codec.encode_message.call_args

        message = encode_call.kwargs['data']
        assert message['type'] == f'ticket_{event_type}'
        assert message['event_id'] == event_id
        assert message['ticket'] == ticket_data
        assert 'timestamp' in message

        # Verify filtered broadcast was used
        mock_connection_manager.broadcast_to_filtered.assert_called_once()
        broadcast_call = mock_connection_manager.broadcast_to_filtered.call_args

        # Test the section filter function
        filter_func = broadcast_call.kwargs['filter_func']

        # User subscribed to affected section
        metadata_affected = {'subscribed_sections': {'A-1'}}
        assert filter_func(metadata_affected) is True

        # User subscribed to both affected sections
        metadata_both = {'subscribed_sections': {'A-1', 'B-2'}}
        assert filter_func(metadata_both) is True

        # User not subscribed to affected sections
        metadata_unaffected = {'subscribed_sections': {'C-3'}}
        assert filter_func(metadata_unaffected) is False

        # User with no subscription (should receive all)
        metadata_no_filter = {'subscribed_sections': set()}
        assert filter_func(metadata_no_filter) is True

    @pytest.mark.asyncio
    async def test_broadcast_ticket_event_to_all_users(
        self, websocket_service, mock_connection_manager, mock_codec
    ):
        """測試廣播票務事件到所有用戶（無過濾）"""
        # Arrange
        event_id = 456
        ticket_data = {
            'event_id': event_id,
            'total_reserved': 5,
            'affected_subsections': ['A-1', 'B-2'],
            'remaining_counts_by_subsection': {'A-1': 10, 'B-2': 8},
        }
        event_type = 'reservation_summary'

        # Act - without affected_sections parameter
        await websocket_service.broadcast_ticket_event(
            event_id=event_id,
            ticket_data=ticket_data,
            event_type=event_type,
            # No affected_sections parameter
        )

        # Assert
        # Verify message encoding
        mock_codec.encode_message.assert_called_once()
        encode_call = mock_codec.encode_message.call_args

        message = encode_call.kwargs['data']
        assert message['type'] == f'ticket_{event_type}'
        assert message['event_id'] == event_id
        assert message['ticket'] == ticket_data

        # Verify broadcast to all users in group
        mock_connection_manager.broadcast_to_group.assert_called_once()
        broadcast_call = mock_connection_manager.broadcast_to_group.call_args

        assert broadcast_call.kwargs['group_id'] == f'event_{event_id}'  # group_id
        assert broadcast_call.kwargs['data'] == b'encoded_message'  # encoded message

        # Should not use filtered broadcast
        mock_connection_manager.broadcast_to_filtered.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_connection_count(self, websocket_service, mock_connection_manager):
        """測試取得連線數量"""
        # Arrange
        event_id = 456
        expected_count = 12

        mock_connection_manager.get_group_size.return_value = expected_count

        # Act
        actual_count = websocket_service.get_connection_count(event_id)

        # Assert
        assert actual_count == expected_count
        mock_connection_manager.get_group_size.assert_called_once_with(group_id=f'event_{event_id}')

    @pytest.mark.asyncio
    async def test_broadcast_subsection_event_encoding_options(
        self, websocket_service, mock_connection_manager, mock_codec
    ):
        """測試分區廣播事件的編碼選項"""
        # Arrange
        event_id = 123
        section = 'VIP'
        subsection = 5
        event_type = 'status_update'
        data = {'status': 'maintenance'}

        # Act
        await websocket_service.broadcast_subsection_event(
            event_id=event_id,
            section=section,
            subsection=subsection,
            event_type=event_type,
            data=data,
        )

        # Assert
        # Verify binary encoding is used
        mock_codec.encode_message.assert_called_once()
        encode_call = mock_codec.encode_message.call_args
        assert encode_call.kwargs['use_binary'] is True

        # Verify message structure
        message = encode_call.kwargs['data']
        assert message['type'] == 'subsection_status_update'
        assert message['event_id'] == event_id
        assert message['section'] == section
        assert message['subsection'] == subsection
        assert message['subsection_id'] == 'VIP-5'
        assert message['data'] == data
