#!/usr/bin/env python3
"""
WebSocket endpoint tests
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.event_ticketing.port.event_controller import websocket_ticket_updates
from src.shared.service.jwt_auth_service import get_jwt_strategy
from src.user.domain.user_model import User, UserRole


class MockWebSocket:
    """Mock WebSocket for testing"""

    def __init__(self, cookies=None):
        self.cookies = cookies or {}
        self.closed = False
        self.close_code = None
        self.close_reason = None
        self.messages_sent = []

    async def close(self, code: int, reason: str):
        self.closed = True
        self.close_code = code
        self.close_reason = reason

    async def send_bytes(self, data: bytes):
        self.messages_sent.append(('bytes', data))

    async def send_text(self, data: str):
        self.messages_sent.append(('text', data))


class TestWebSocketEndpoint:
    @pytest.mark.asyncio
    async def test_websocket_missing_cookie(self):
        """Test WebSocket rejects connection without auth cookie"""
        websocket = MockWebSocket()

        await websocket_ticket_updates(websocket, event_id=1)  # type: ignore
        assert websocket.closed
        assert websocket.close_code == 4001
        assert websocket.close_reason == 'Missing auth cookie'

    @pytest.mark.asyncio
    async def test_websocket_invalid_token(self):
        """Test WebSocket rejects invalid JWT token"""
        websocket = MockWebSocket(cookies={'fastapiusersauth': 'invalid_token'})

        await websocket_ticket_updates(websocket, event_id=1)  # type: ignore
        assert websocket.closed
        assert websocket.close_code == 4001
        assert websocket.close_reason == 'Invalid token'

    @pytest.mark.asyncio
    async def test_websocket_valid_authentication(self):
        """Test WebSocket accepts valid JWT token and connects"""
        user = User(
            id=123,
            email='test@example.com',
            name='Test User',
            role=UserRole.BUYER,
            hashed_password='test',
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )

        jwt_strategy = get_jwt_strategy()
        valid_token = await jwt_strategy.write_token(user)

        websocket = MockWebSocket(cookies={'fastapiusersauth': valid_token})
        with patch(
            'src.event_ticketing.port.event_controller.ticket_websocket_service'
        ) as mock_service:
            mock_service.handle_connection = AsyncMock()

            await websocket_ticket_updates(websocket, event_id=1)  # type: ignore
            assert not websocket.closed

            mock_service.handle_connection.assert_called_once()
            call_args = mock_service.handle_connection.call_args
            assert call_args[0][0] == websocket
            assert call_args[0][1] == 1

            passed_user = call_args[0][2]
            assert passed_user.id == 123
            assert passed_user.email == 'test@example.com'
            assert passed_user.role == UserRole.BUYER
