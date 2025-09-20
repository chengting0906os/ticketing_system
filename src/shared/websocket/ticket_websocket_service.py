import asyncio
from typing import Dict, List, Optional

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from src.shared.websocket.connection_manager import WebSocketConnectionManager
from src.shared.websocket.message_codec import WebSocketMessageCodec
from src.shared.websocket.message_handlers import (
    TicketEventBroadcaster,
    WebSocketMessageHandler,
)
from src.shared.websocket.websocket_config import WebSocketConfig, WebSocketErrorMessages
from src.user.domain.user_model import User


class TicketWebSocketService:
    def __init__(
        self,
        ping_interval: float = WebSocketConfig.DEFAULT_PING_INTERVAL,
        ping_timeout: float = WebSocketConfig.DEFAULT_PING_TIMEOUT,
    ):
        self.connection_manager = WebSocketConnectionManager()
        self.codec = WebSocketMessageCodec()
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout

        # Initialize message handlers
        self.message_handler = WebSocketMessageHandler(self.connection_manager, self.codec, self)
        self.event_broadcaster = TicketEventBroadcaster(self.connection_manager, self.codec)

    async def handle_connection(self, websocket: WebSocket, event_id: int, user: User):
        group_id = f'event_{event_id}'
        metadata = {
            'user_id': user.id,
            'user_role': user.role,
            'event_id': event_id,
            'subscribed_sections': set(),
        }

        await self.connection_manager.connect(
            websocket=websocket, group_id=group_id, metadata=metadata
        )

        # Send welcome message
        welcome_msg = {
            'type': WebSocketConfig.MessageType.CONNECTED,
            'event_id': event_id,
            'user_id': user.id,
            'message': 'Connected to ticket updates',
        }
        await self.send_message(websocket, welcome_msg)

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
            await self.connection_manager.disconnect(websocket=websocket)

    async def _ping_loop(self, websocket: WebSocket):
        while True:
            try:
                await asyncio.sleep(self.ping_interval)

                # Send application-level ping message
                ping_msg = {
                    'type': WebSocketConfig.MessageType.PING,
                    'timestamp': asyncio.get_event_loop().time(),
                }
                await self.send_message(websocket, ping_msg)

                # WebSocket protocol-level ping/pong is handled automatically by FastAPI/Starlette

            except (WebSocketDisconnect, ConnectionError):
                # Connection is dead, break the loop
                break
            except Exception as e:
                # Log unexpected errors but break to be safe
                logger.error(f'Unexpected error in ping loop: {e}')
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
                    message = self.codec.decode_message(raw_data=raw_message['text'])
                elif 'bytes' in raw_message:
                    message = self.codec.decode_message(raw_data=raw_message['bytes'])
                else:
                    continue

                await self.message_handler.handle_message(websocket, message)

            except ValueError as e:
                error_msg = {
                    'type': WebSocketConfig.MessageType.ERROR,
                    'message': f'{WebSocketErrorMessages.INVALID_MESSAGE_FORMAT}: {str(e)}',
                }
                success = await self.send_message(websocket, error_msg, use_binary=False)
                if not success:
                    # If we can't send error message, connection is likely dead
                    break

    # Message processing is now handled by WebSocketMessageHandler

    async def send_message(
        self, websocket: WebSocket, message: Dict, use_binary: bool = True
    ) -> bool:
        """Send message to WebSocket connection

        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        try:
            if use_binary:
                encoded_data = self.codec.encode_message(data=message, use_binary=True)
                if isinstance(encoded_data, bytes):
                    await websocket.send_bytes(encoded_data)
                else:
                    # Fallback to text if encoding didn't return bytes
                    await websocket.send_text(str(encoded_data))
            else:
                encoded_data = self.codec.encode_message(data=message, use_binary=False)
                if isinstance(encoded_data, str):
                    await websocket.send_text(encoded_data)
                else:
                    # Convert to string if encoding didn't return string
                    await websocket.send_text(str(encoded_data))
            return True
        except (WebSocketDisconnect, ConnectionError):
            # Connection already closed, will be cleaned up by connection manager
            return False
        except Exception as e:
            # Log unexpected errors but don't crash the service
            logger.error(f'Unexpected error sending WebSocket message: {e}')
            return False

    async def broadcast_ticket_event(
        self,
        event_id: int,
        ticket_data: Dict,
        event_type: str,
        affected_sections: Optional[List[str]] = None,
    ) -> None:
        """Delegate to event broadcaster."""
        await self.event_broadcaster.broadcast_ticket_event(
            event_id=event_id,
            ticket_data=ticket_data,
            event_type=event_type,
            affected_sections=affected_sections,
        )

    async def broadcast_subsection_event(
        self,
        event_id: int,
        section: str,
        subsection: int,
        event_type: str,
        data: Dict,
    ) -> None:
        """Delegate to event broadcaster."""
        await self.event_broadcaster.broadcast_subsection_event(
            event_id=event_id,
            section=section,
            subsection=subsection,
            event_type=event_type,
            data=data,
        )

    def get_connection_count(self, event_id: int) -> int:
        """Get the number of active connections for an event."""
        group_id = f'event_{event_id}'
        return self.connection_manager.get_group_size(group_id=group_id)


# Global instance with default settings
ticket_websocket_service = TicketWebSocketService()
