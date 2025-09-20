#!/usr/bin/env python3
"""
WebSocket ping-pong and message handling tests
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.shared.websocket.message_codec import WebSocketMessageCodec
from src.shared.websocket.ticket_websocket_service import TicketWebSocketService
from src.user.domain.user_model import User, UserRole


class MockWebSocket:
    """Mock WebSocket for testing"""

    def __init__(self, cookies=None):
        self.cookies = cookies or {}
        self.closed = False
        self.close_code = None
        self.close_reason = None
        self.messages_sent = []
        self.messages_to_receive = []
        self.receive_index = 0

    async def close(self, code: int, reason: str):
        self.closed = True
        self.close_code = code
        self.close_reason = reason

    async def send_bytes(self, data: bytes):
        self.messages_sent.append(('bytes', data))

    async def send_text(self, data: str):
        self.messages_sent.append(('text', data))

    def add_message_to_receive(self, message_type: str, content):
        """Add a message that will be returned by receive()"""
        if isinstance(content, dict):
            import json

            content = json.dumps(content)

        self.messages_to_receive.append(
            {'type': message_type, 'text' if isinstance(content, str) else 'bytes': content}
        )

    async def receive(self):
        """Mock receive method that returns pre-configured messages"""
        if self.receive_index < len(self.messages_to_receive):
            message = self.messages_to_receive[self.receive_index]
            self.receive_index += 1
            return message
        return {'type': 'websocket.disconnect'}


class TestWebSocketMessageHandling:
    @pytest.mark.asyncio
    async def test_ping_pong_mechanism(self):
        """Test application-level ping-pong mechanism"""
        websocket = MockWebSocket()
        ping_request = {'action': 'ping'}
        websocket.add_message_to_receive('websocket.receive', ping_request)
        service = TicketWebSocketService(ping_interval=0.1, ping_timeout=1.0)
        with (
            patch.object(service.connection_manager, 'connect', new_callable=AsyncMock),
            patch.object(service.connection_manager, 'disconnect', new_callable=AsyncMock),
        ):
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

            connection_task = asyncio.create_task(
                service.handle_connection(websocket, event_id=1, user=user)  # type: ignore
            )
            await asyncio.sleep(0.2)
            connection_task.cancel()
            assert len(websocket.messages_sent) >= 2

            codec = WebSocketMessageCodec()

            message_types = []
            for msg_type, data in websocket.messages_sent:
                if msg_type == 'bytes':
                    decoded = codec.decode_message(raw_data=data)
                    message_types.append(decoded.get('type'))

            assert 'connected' in message_types
            assert any(msg_type in ['ping', 'pong'] for msg_type in message_types)

    @pytest.mark.asyncio
    async def test_unknown_action_handling(self):
        """Test that unknown actions receive error responses"""
        websocket = MockWebSocket()
        unknown_request = {'action': 'unknown_action'}
        websocket.add_message_to_receive('websocket.receive', unknown_request)

        service = TicketWebSocketService(ping_interval=10.0)
        with (
            patch.object(service.connection_manager, 'connect', new_callable=AsyncMock),
            patch.object(service.connection_manager, 'disconnect', new_callable=AsyncMock),
        ):
            user = User(
                id=456,
                email='test@example.com',
                name='Test User',
                role=UserRole.SELLER,
                hashed_password='test',
                is_active=True,
                is_superuser=False,
                is_verified=True,
            )

            connection_task = asyncio.create_task(
                service.handle_connection(websocket, event_id=2, user=user)  # type: ignore
            )

            await asyncio.sleep(0.1)
            connection_task.cancel()

            codec = WebSocketMessageCodec()

            error_response_found = False
            for msg_type, data in websocket.messages_sent:
                if msg_type == 'bytes':
                    decoded = codec.decode_message(raw_data=data)
                    if decoded.get('type') == 'error':
                        error_response_found = True
                        assert 'Unknown action: unknown_action' in decoded.get('message', '')
                        break

            assert error_response_found, 'Error response for unknown action not found'

    @pytest.mark.asyncio
    async def test_ping_timeout_behavior(self):
        """Test service handles ping loop correctly"""
        websocket = MockWebSocket()

        service = TicketWebSocketService(ping_interval=0.05, ping_timeout=0.1)
        ping_task = asyncio.create_task(service._ping_loop(websocket))  # type: ignore
        await asyncio.sleep(0.15)
        ping_task.cancel()
        assert len(websocket.messages_sent) >= 1

        codec = WebSocketMessageCodec()

        ping_found = False
        for msg_type, data in websocket.messages_sent:
            if msg_type == 'bytes':
                decoded = codec.decode_message(raw_data=data)
                if decoded.get('type') == 'ping':
                    ping_found = True
                    assert 'timestamp' in decoded
                    break

        assert ping_found, 'Ping message not found'

    @pytest.mark.asyncio
    async def test_concurrent_ping_and_messages(self):
        """Test ping loop and message handling work concurrently"""
        websocket = MockWebSocket()
        websocket.add_message_to_receive('websocket.receive', {'action': 'ping'})
        websocket.add_message_to_receive('websocket.receive', {'action': 'unknown_action'})
        websocket.add_message_to_receive('websocket.receive', {'action': 'get_current_status'})

        service = TicketWebSocketService(ping_interval=0.1, ping_timeout=1.0)

        with (
            patch.object(service.connection_manager, 'connect', new_callable=AsyncMock),
            patch.object(service.connection_manager, 'disconnect', new_callable=AsyncMock),
        ):
            user = User(
                id=789,
                email='concurrent@example.com',
                name='Concurrent User',
                role=UserRole.BUYER,
                hashed_password='test',
                is_active=True,
                is_superuser=False,
                is_verified=True,
            )

            connection_task = asyncio.create_task(
                service.handle_connection(websocket, event_id=3, user=user)  # type: ignore
            )
            await asyncio.sleep(0.25)
            connection_task.cancel()
            from src.shared.websocket.message_codec import WebSocketMessageCodec

            codec = WebSocketMessageCodec()

            message_types = []
            for msg_type, data in websocket.messages_sent:
                if msg_type == 'bytes':
                    decoded = codec.decode_message(raw_data=data)
                    message_types.append(decoded.get('type'))

            found_types = set(message_types)

            assert 'connected' in found_types
            assert len(found_types.intersection({'pong', 'error', 'status_requested', 'ping'})) >= 2
