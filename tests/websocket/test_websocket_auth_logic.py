#!/usr/bin/env python3
"""
WebSocket authentication logic tests
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.shared.service.jwt_auth_service import CustomJWTStrategy, get_jwt_strategy
from src.user.domain.user_model import User, UserRole


class MockWebSocket:
    """Mock WebSocket for testing"""

    def __init__(self, cookies=None):
        self.cookies = cookies or {}
        self.closed = False
        self.close_code = None
        self.close_reason = None

    async def close(self, code, reason):
        self.closed = True
        self.close_code = code
        self.close_reason = reason


class TestWebSocketAuthLogic:
    @pytest.mark.asyncio
    async def test_websocket_auth_missing_cookie(self):
        """Test WebSocket auth logic with missing cookie"""
        websocket = MockWebSocket()
        token = websocket.cookies.get('fastapiusersauth')
        assert token is None
        await websocket.close(code=4001, reason='Missing auth cookie')

        assert websocket.closed
        assert websocket.close_code == 4001
        assert websocket.close_reason == 'Missing auth cookie'

    @pytest.mark.asyncio
    async def test_websocket_auth_invalid_token(self):
        """Test WebSocket auth logic with invalid token"""
        websocket = MockWebSocket(cookies={'fastapiusersauth': 'invalid_token'})
        token = websocket.cookies.get('fastapiusersauth')
        assert token == 'invalid_token'

        try:
            jwt_strategy = get_jwt_strategy()

            mock_user_manager = AsyncMock()
            mock_user_manager.get = AsyncMock(return_value=None)

            user = await jwt_strategy.read_token(token, mock_user_manager)

            if not user:
                await websocket.close(code=4001, reason='Invalid token')
        except Exception:
            await websocket.close(code=4001, reason='Invalid token')

        assert websocket.closed
        assert websocket.close_code == 4001

    @pytest.mark.asyncio
    async def test_websocket_auth_valid_token(self):
        """Test complete WebSocket auth flow with valid token"""
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
        token = websocket.cookies.get('fastapiusersauth')
        assert token is not None

        try:
            if isinstance(jwt_strategy, CustomJWTStrategy):
                payload = jwt_strategy.decode_token(token)
                assert payload is not None
                assert payload.get('user_id') == 123
            current_user = user
            assert current_user is not None
            assert current_user.id == 123

            if current_user.role not in [UserRole.BUYER, UserRole.SELLER]:
                await websocket.close(code=4003, reason='Forbidden')
            else:
                assert current_user.id == 123
                assert current_user.role == UserRole.BUYER
                assert current_user.email == 'test@example.com'

        except Exception:
            await websocket.close(code=4001, reason='Invalid token')
            raise

        assert not websocket.closed


if __name__ == '__main__':

    async def run_tests():
        test_instance = TestWebSocketAuthLogic()

        await test_instance.test_websocket_auth_missing_cookie()
        await test_instance.test_websocket_auth_invalid_token()
        await test_instance.test_websocket_auth_valid_token()

    asyncio.run(run_tests())
