"""WebSocket message handlers for different message types."""

import asyncio
from typing import Dict, List, Optional, Protocol

from fastapi import WebSocket

from src.shared.websocket.connection_manager import WebSocketConnectionManager
from src.shared.websocket.message_codec import WebSocketMessageCodec
from src.shared.websocket.websocket_config import WebSocketConfig, WebSocketErrorMessages


class MessageSender(Protocol):
    """Protocol for sending messages through WebSocket."""

    async def send_message(
        self, websocket: WebSocket, message: Dict, use_binary: bool = True
    ) -> bool:
        """Send a message through WebSocket connection."""
        ...


class WebSocketMessageHandler:
    """Base class for WebSocket message handling."""

    def __init__(
        self,
        connection_manager: WebSocketConnectionManager,
        codec: WebSocketMessageCodec,
        message_sender: MessageSender,
    ):
        self.connection_manager = connection_manager
        self.codec = codec
        self.message_sender = message_sender

    async def handle_message(self, websocket: WebSocket, message: Dict) -> None:
        """Handle incoming WebSocket message."""
        action = message.get('action')

        if action == WebSocketConfig.ActionType.SUBSCRIBE_SECTIONS:
            await self._handle_section_subscription(websocket, message.get('sections', []))
        elif action == WebSocketConfig.ActionType.PING:
            await self._handle_ping(websocket)
        elif action == WebSocketConfig.ActionType.GET_CURRENT_STATUS:
            await self._handle_status_request(websocket)
        else:
            error_msg = {
                'type': WebSocketConfig.MessageType.ERROR,
                'message': f'{WebSocketErrorMessages.UNKNOWN_ACTION}: {action}',
            }
            await self.message_sender.send_message(websocket, error_msg)

    async def _handle_section_subscription(self, websocket: WebSocket, sections: List[str]) -> None:
        """Handle section subscription request with validation."""
        metadata = self.connection_manager.get_connection_metadata(websocket=websocket)
        if not metadata:
            error_msg = {
                'type': WebSocketConfig.MessageType.ERROR,
                'message': WebSocketErrorMessages.CONNECTION_METADATA_NOT_FOUND,
            }
            await self.message_sender.send_message(websocket, error_msg)
            return

        # Validate sections format
        if not isinstance(sections, list) or not all(isinstance(s, str) for s in sections):
            error_msg = {
                'type': WebSocketConfig.MessageType.ERROR,
                'message': WebSocketErrorMessages.SECTIONS_MUST_BE_LIST,
            }
            await self.message_sender.send_message(websocket, error_msg)
            return

        metadata['subscribed_sections'] = set(sections)
        self.connection_manager.update_connection_metadata(websocket=websocket, metadata=metadata)

        response = {
            'type': WebSocketConfig.MessageType.SUBSCRIPTION_CONFIRMED,
            'subscribed_sections': sections,
        }
        await self.message_sender.send_message(websocket, response)

    async def _handle_ping(self, websocket: WebSocket) -> None:
        """Handle ping request."""
        response = {
            'type': WebSocketConfig.MessageType.PONG,
            'timestamp': asyncio.get_event_loop().time(),
        }
        await self.message_sender.send_message(websocket, response)

    async def _handle_status_request(self, websocket: WebSocket) -> None:
        """Handle status request."""
        response = {
            'type': WebSocketConfig.MessageType.STATUS_REQUESTED,
            'message': WebSocketErrorMessages.USE_API_FOR_INITIAL_DATA,
        }
        await self.message_sender.send_message(websocket, response)


class TicketEventBroadcaster:
    """Handles broadcasting of ticket-related events."""

    def __init__(
        self,
        connection_manager: WebSocketConnectionManager,
        codec: WebSocketMessageCodec,
    ):
        self.connection_manager = connection_manager
        self.codec = codec

    async def broadcast_ticket_event(
        self,
        *,
        event_id: int,
        ticket_data: Dict,
        event_type: str,
        affected_sections: Optional[List[str]] = None,
    ) -> None:
        """Broadcast general ticket event to event subscribers."""
        group_id = self._build_group_id(event_id)

        message = {
            'type': f'ticket_{event_type}',
            'event_id': event_id,
            'ticket': ticket_data,
            'timestamp': asyncio.get_event_loop().time(),
        }

        encoded_message = self.codec.encode_message(data=message, use_binary=True)

        if affected_sections:
            section_filter = self._create_section_filter(affected_sections)
            await self.connection_manager.broadcast_to_filtered(
                group_id=group_id,
                data=encoded_message,  # type: ignore
                filter_func=section_filter,
            )
        else:
            await self.connection_manager.broadcast_to_group(
                group_id=group_id,
                data=encoded_message,  # type: ignore
            )  # type: ignore

    async def broadcast_subsection_event(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        event_type: str,
        data: Dict,
    ) -> None:
        """Broadcast events specifically for a subsection to relevant subscribers."""
        group_id = self._build_group_id(event_id)
        subsection_identifier = f'{section}-{subsection}'

        message = {
            'type': f'subsection_{event_type}',
            'event_id': event_id,
            'section': section,
            'subsection': subsection,
            'subsection_id': subsection_identifier,
            'data': data,
            'timestamp': asyncio.get_event_loop().time(),
        }

        encoded_message = self.codec.encode_message(data=message, use_binary=True)

        # Filter to connections subscribed to this specific subsection
        subsection_filter = self._create_subsection_filter(subsection_identifier, section, event_id)

        await self.connection_manager.broadcast_to_filtered(
            group_id=group_id,
            data=encoded_message,  # type: ignore
            filter_func=subsection_filter,
        )

    def _build_group_id(self, event_id: int) -> str:
        """Build group ID for event subscriptions."""
        return f'event_{event_id}'

    def _create_section_filter(self, affected_sections: List[str]):
        """Create filter function for section-based broadcasting."""

        def section_filter(metadata: Dict) -> bool:
            subscribed_sections = metadata.get('subscribed_sections', set())
            if not subscribed_sections:  # No subscription filter, send to all
                return True
            return bool(subscribed_sections.intersection(affected_sections))

        return section_filter

    def _create_subsection_filter(self, subsection_identifier: str, section: str, event_id: int):
        """Create filter function for subsection-based broadcasting."""

        def subsection_filter(metadata: Dict) -> bool:
            subscribed_sections = metadata.get('subscribed_sections', set())
            if not subscribed_sections:  # No subscription filter, send to all
                return True

            # Check if user is subscribed to this specific subsection or the general section
            return (
                subsection_identifier in subscribed_sections
                or section in subscribed_sections
                or f'event_{event_id}' in subscribed_sections
            )

        return subsection_filter
