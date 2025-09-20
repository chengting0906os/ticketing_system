#!/usr/bin/env python3
"""
WebSocket 連線過濾和廣播邏輯單元測試
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.shared.websocket.connection_manager import WebSocketConnectionManager


class TestWebSocketConnectionFiltering:
    """WebSocket 連線過濾和廣播邏輯單元測試"""

    @pytest.fixture
    def connection_manager(self):
        """Create WebSocketConnectionManager instance"""
        return WebSocketConnectionManager()

    @pytest.fixture
    def mock_websockets(self):
        """Create mock WebSocket connections"""
        ws1 = MagicMock()
        ws1.send_bytes = AsyncMock()
        ws1.send_text = AsyncMock()
        ws1.accept = AsyncMock()

        ws2 = MagicMock()
        ws2.send_bytes = AsyncMock()
        ws2.send_text = AsyncMock()
        ws2.accept = AsyncMock()

        ws3 = MagicMock()
        ws3.send_bytes = AsyncMock()
        ws3.send_text = AsyncMock()
        ws3.accept = AsyncMock()

        return [ws1, ws2, ws3]

    @pytest.mark.asyncio
    async def test_filtered_broadcast_by_subscription(self, connection_manager, mock_websockets):
        """測試基於訂閱的過濾廣播"""
        # Arrange
        group_id = 'event_456'
        message = b'test_message'

        # Setup connections with different subscriptions
        metadata1 = {'user_id': 1, 'event_id': 456, 'subscribed_sections': {'A-1', 'B-2'}}

        metadata2 = {'user_id': 2, 'event_id': 456, 'subscribed_sections': {'C-3'}}

        metadata3 = {
            'user_id': 3,
            'event_id': 456,
            'subscribed_sections': set(),  # No specific subscription
        }

        # Connect all websockets
        await connection_manager.connect(
            websocket=mock_websockets[0], group_id=group_id, metadata=metadata1
        )
        await connection_manager.connect(
            websocket=mock_websockets[1], group_id=group_id, metadata=metadata2
        )
        await connection_manager.connect(
            websocket=mock_websockets[2], group_id=group_id, metadata=metadata3
        )

        # Define filter function - only send to users subscribed to A-1 or users with no filter
        def section_filter(metadata):
            subscribed_sections = metadata.get('subscribed_sections', set())
            if not subscribed_sections:  # No subscription filter
                return True
            return 'A-1' in subscribed_sections

        # Act
        await connection_manager.broadcast_to_filtered(
            group_id=group_id, data=message, filter_func=section_filter
        )

        # Assert
        # WebSocket 1 should receive (subscribed to A-1)
        mock_websockets[0].send_bytes.assert_called_once_with(message)

        # WebSocket 2 should NOT receive (subscribed to C-3)
        mock_websockets[1].send_bytes.assert_not_called()

        # WebSocket 3 should receive (no subscription filter)
        mock_websockets[2].send_bytes.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_filtered_broadcast_multiple_criteria(self, connection_manager, mock_websockets):
        """測試多條件過濾廣播"""
        # Arrange
        group_id = 'event_789'
        message = b'complex_filter_message'

        # Setup connections with different user roles and subscriptions
        metadata1 = {
            'user_id': 1,
            'user_role': 'buyer',
            'event_id': 789,
            'subscribed_sections': {'A-1'},
        }

        metadata2 = {
            'user_id': 2,
            'user_role': 'seller',
            'event_id': 789,
            'subscribed_sections': {'A-1', 'B-2'},
        }

        metadata3 = {
            'user_id': 3,
            'user_role': 'admin',
            'event_id': 789,
            'subscribed_sections': {'C-3'},
        }

        # Connect all websockets
        await connection_manager.connect(
            websocket=mock_websockets[0], group_id=group_id, metadata=metadata1
        )
        await connection_manager.connect(
            websocket=mock_websockets[1], group_id=group_id, metadata=metadata2
        )
        await connection_manager.connect(
            websocket=mock_websockets[2], group_id=group_id, metadata=metadata3
        )

        # Define complex filter - admin users OR users subscribed to A-1
        def complex_filter(metadata):
            user_role = metadata.get('user_role')
            subscribed_sections = metadata.get('subscribed_sections', set())

            # Admin users always receive
            if user_role == 'admin':
                return True

            # Users subscribed to A-1
            return 'A-1' in subscribed_sections

        # Act
        await connection_manager.broadcast_to_filtered(
            group_id=group_id, data=message, filter_func=complex_filter
        )

        # Assert
        # WebSocket 1 should receive (subscribed to A-1)
        mock_websockets[0].send_bytes.assert_called_once_with(message)

        # WebSocket 2 should receive (subscribed to A-1)
        mock_websockets[1].send_bytes.assert_called_once_with(message)

        # WebSocket 3 should receive (admin role)
        mock_websockets[2].send_bytes.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_broadcast_to_group_all_users(self, connection_manager, mock_websockets):
        """測試廣播到群組所有用戶"""
        # Arrange
        group_id = 'event_999'
        message = b'broadcast_all_message'

        # Setup connections with different metadata
        metadata1 = {'user_id': 1, 'event_id': 999, 'subscribed_sections': {'A-1'}}
        metadata2 = {'user_id': 2, 'event_id': 999, 'subscribed_sections': {'B-2'}}
        metadata3 = {'user_id': 3, 'event_id': 999, 'subscribed_sections': set()}

        # Connect all websockets
        await connection_manager.connect(
            websocket=mock_websockets[0], group_id=group_id, metadata=metadata1
        )
        await connection_manager.connect(
            websocket=mock_websockets[1], group_id=group_id, metadata=metadata2
        )
        await connection_manager.connect(
            websocket=mock_websockets[2], group_id=group_id, metadata=metadata3
        )

        # Act
        await connection_manager.broadcast_to_group(group_id=group_id, data=message)

        # Assert
        # All websockets should receive the message
        mock_websockets[0].send_bytes.assert_called_once_with(message)
        mock_websockets[1].send_bytes.assert_called_once_with(message)
        mock_websockets[2].send_bytes.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_filtered_broadcast_with_connection_errors(
        self, connection_manager, mock_websockets
    ):
        """測試過濾廣播時的連線錯誤處理"""
        # Arrange
        group_id = 'event_error_test'
        message = b'error_test_message'

        # Setup connections
        metadata1 = {'user_id': 1, 'subscribed_sections': {'A-1'}}
        metadata2 = {'user_id': 2, 'subscribed_sections': {'A-1'}}

        await connection_manager.connect(
            websocket=mock_websockets[0], group_id=group_id, metadata=metadata1
        )
        await connection_manager.connect(
            websocket=mock_websockets[1], group_id=group_id, metadata=metadata2
        )

        # Make one websocket fail
        mock_websockets[0].send_bytes.side_effect = Exception('Connection lost')

        # Filter to send to both users
        def allow_all_filter(_metadata):
            return True

        # Act - should not raise exception even if one connection fails
        await connection_manager.broadcast_to_filtered(
            group_id=group_id, data=message, filter_func=allow_all_filter
        )

        # Assert
        # Failed connection should still be attempted
        mock_websockets[0].send_bytes.assert_called_once_with(message)

        # Working connection should receive message
        mock_websockets[1].send_bytes.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_metadata_update_affects_filtering(self, connection_manager, mock_websockets):
        """測試元數據更新對過濾的影響"""
        # Arrange
        group_id = 'event_metadata_test'
        message = b'metadata_test_message'

        # Initial metadata - not subscribed to target section
        initial_metadata = {'user_id': 1, 'event_id': 123, 'subscribed_sections': {'B-2'}}

        # Connect websocket
        await connection_manager.connect(
            websocket=mock_websockets[0], group_id=group_id, metadata=initial_metadata
        )

        # Filter for A-1 subscribers only
        def a1_filter(metadata):
            subscribed_sections = metadata.get('subscribed_sections', set())
            return 'A-1' in subscribed_sections

        # Act 1 - broadcast before metadata update
        await connection_manager.broadcast_to_filtered(
            group_id=group_id, data=message, filter_func=a1_filter
        )

        # Assert 1 - should not receive (not subscribed to A-1)
        mock_websockets[0].send_bytes.assert_not_called()

        # Update metadata - now subscribed to A-1
        updated_metadata = {'user_id': 1, 'event_id': 123, 'subscribed_sections': {'A-1', 'B-2'}}
        connection_manager.update_connection_metadata(
            websocket=mock_websockets[0], metadata=updated_metadata
        )

        # Act 2 - broadcast after metadata update
        await connection_manager.broadcast_to_filtered(
            group_id=group_id, data=message, filter_func=a1_filter
        )

        # Assert 2 - should now receive (subscribed to A-1)
        mock_websockets[0].send_bytes.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_get_group_size_with_filtering_context(self, connection_manager, mock_websockets):
        """測試在過濾上下文中取得群組大小"""
        # Arrange
        group_id = 'event_size_test'

        # Connect multiple websockets
        metadata1 = {'user_id': 1, 'subscribed_sections': {'A-1'}}
        metadata2 = {'user_id': 2, 'subscribed_sections': {'B-2'}}
        metadata3 = {'user_id': 3, 'subscribed_sections': {'A-1', 'B-2'}}

        await connection_manager.connect(
            websocket=mock_websockets[0], group_id=group_id, metadata=metadata1
        )
        await connection_manager.connect(
            websocket=mock_websockets[1], group_id=group_id, metadata=metadata2
        )
        await connection_manager.connect(
            websocket=mock_websockets[2], group_id=group_id, metadata=metadata3
        )

        # Act
        group_size = connection_manager.get_group_size(group_id=group_id)

        # Assert
        assert group_size == 3

        # Test after disconnection
        await connection_manager.disconnect(websocket=mock_websockets[1])
        group_size_after_disconnect = connection_manager.get_group_size(group_id=group_id)
        assert group_size_after_disconnect == 2
