import asyncio
from typing import Dict, List, Optional

from fastapi import WebSocket, WebSocketDisconnect

from src.shared.websocket.connection_manager import WebSocketConnectionManager
from src.shared.websocket.message_codec import WebSocketMessageCodec
from src.user.domain.user_model import User


class TicketWebSocketService:
    def __init__(self, ping_interval: float = 30.0, ping_timeout: float = 30.0):
        self.connection_manager = WebSocketConnectionManager()
        self.codec = WebSocketMessageCodec()
        self.ping_interval = ping_interval  # Send ping every 30 seconds
        self.ping_timeout = ping_timeout  # Wait 10 seconds for pong response

    async def handle_connection(self, websocket: WebSocket, event_id: int, user: User):
        group_id = f'event_{event_id}'
        metadata = {
            'user_id': user.id,
            'user_role': user.role,
            'event_id': event_id,
            'subscribed_sections': set(),
        }

        await self.connection_manager.connect(websocket, group_id, metadata)

        # Send welcome message
        welcome_msg = {
            'type': 'connected',
            'event_id': event_id,
            'user_id': user.id,
            'message': 'Connected to ticket updates',
        }
        await self._send_message(websocket, welcome_msg)

        try:
            # Start ping task and message handling concurrently
            ping_task = asyncio.create_task(self._ping_loop(websocket))
            message_task = asyncio.create_task(self._handle_messages(websocket))

            # Wait for either task to complete (usually due to disconnection)
            _, pending = await asyncio.wait(
                {ping_task, message_task}, return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel remaining tasks
            for task in pending:
                task.cancel()

        except WebSocketDisconnect:
            pass
        finally:
            await self.connection_manager.disconnect(websocket)

    async def _ping_loop(self, websocket: WebSocket):
        while True:
            try:
                await asyncio.sleep(self.ping_interval)

                # Send application-level ping message
                ping_msg = {'type': 'ping', 'timestamp': asyncio.get_event_loop().time()}
                await self._send_message(websocket, ping_msg)

                # WebSocket protocol-level ping/pong is handled automatically by FastAPI/Starlette

            except (WebSocketDisconnect, ConnectionError):
                # Connection is dead, break the loop
                break
            except Exception:
                # Other errors, also break to be safe
                break

    async def _handle_messages(self, websocket: WebSocket):
        while True:
            raw_message = await websocket.receive()

            if raw_message['type'] == 'websocket.disconnect':
                raise WebSocketDisconnect()
            elif raw_message['type'] != 'websocket.receive':
                continue

            try:
                if 'text' in raw_message:
                    message = self.codec.decode_message(raw_message['text'])
                elif 'bytes' in raw_message:
                    message = self.codec.decode_message(raw_message['bytes'])
                else:
                    continue

                await self._process_message(websocket, message)

            except ValueError as e:
                error_msg = {'type': 'error', 'message': f'Invalid message format: {str(e)}'}
                await self._send_message(websocket, error_msg, use_binary=False)

    async def _process_message(self, websocket: WebSocket, message: Dict):
        action = message.get('action')

        if action == 'subscribe_sections':
            await self._handle_section_subscription(websocket, message.get('sections', []))
        elif action == 'ping':
            await self._handle_ping(websocket)
        elif action == 'get_current_status':
            await self._handle_status_request(websocket)
        else:
            error_msg = {'type': 'error', 'message': f'Unknown action: {action}'}
            await self._send_message(websocket, error_msg)

    async def _handle_section_subscription(self, websocket: WebSocket, sections: List[str]):
        metadata = self.connection_manager.get_connection_metadata(websocket)
        if metadata:
            metadata['subscribed_sections'] = set(sections)
            self.connection_manager.update_connection_metadata(websocket, metadata)

            response = {'type': 'subscription_confirmed', 'subscribed_sections': sections}
            await self._send_message(websocket, response)

    async def _handle_ping(self, websocket: WebSocket):
        response = {'type': 'pong', 'timestamp': asyncio.get_event_loop().time()}
        await self._send_message(websocket, response)

    async def _handle_status_request(self, websocket: WebSocket):
        response = {
            'type': 'status_requested',
            'message': 'Use regular API endpoints for initial data load',
        }
        await self._send_message(websocket, response)

    async def _send_message(self, websocket: WebSocket, message: Dict, use_binary: bool = True):
        try:
            if use_binary:
                data = self.codec.encode_message(message, use_binary=True)
                await websocket.send_bytes(data)  # type: ignore
            else:
                data = self.codec.encode_message(message, use_binary=False)
                await websocket.send_text(data)  # type: ignore
        except Exception:
            # Connection already closed, will be cleaned up
            pass

    async def broadcast_ticket_event(
        self,
        event_id: int,
        ticket_data: Dict,
        event_type: str,
        affected_sections: Optional[List[str]] = None,
    ):
        group_id = f'event_{event_id}'

        message = {
            'type': f'ticket_{event_type}',
            'event_id': event_id,
            'ticket': ticket_data,
            'timestamp': asyncio.get_event_loop().time(),
        }

        encoded_message = self.codec.encode_message(message, use_binary=True)  # type: ignore

        if affected_sections:
            # Filter to connections subscribed to affected sections
            def section_filter(metadata):
                subscribed = metadata.get('subscribed_sections', set())
                return not subscribed or bool(subscribed.intersection(affected_sections))

            await self.connection_manager.broadcast_to_filtered(
                group_id,
                encoded_message,  # type: ignore
                section_filter,  # type: ignore
            )
        else:
            await self.connection_manager.broadcast_to_group(group_id, encoded_message)  # type: ignore

    def get_connection_count(self, event_id: int) -> int:
        group_id = f'event_{event_id}'
        return self.connection_manager.get_group_size(group_id)


# Global instance with 30-second ping interval
ticket_websocket_service = TicketWebSocketService(ping_interval=30.0, ping_timeout=30.0)
