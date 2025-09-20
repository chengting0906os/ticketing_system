"""
SSE Message Codec

Extends the protocol-agnostic MessageCodec to format Server-Sent Events.
Supports both binary (MessagePack) and text (JSON) encoding over HTTP/2.
"""

import base64
from typing import Any, Dict, Optional, Union

from src.shared.message_codec import MessageCodec
from src.shared.sse.sse_config import SSEConfig


class SSEMessageCodec(MessageCodec):
    """SSE-specific message codec with event formatting"""

    @staticmethod
    def format_sse_event(
        *,
        event_type: str,
        data: Union[str, bytes, Dict[str, Any]],
        event_id: Optional[str] = None,
        retry: Optional[int] = None,
        use_binary: bool = True,
    ) -> str:
        """Format data as Server-Sent Event

        Args:
            event_type: Type of the event
            data: Event data (dict will be encoded, str/bytes used directly)
            event_id: Optional event ID for client-side tracking
            retry: Optional retry interval in milliseconds
            use_binary: Whether to use MessagePack encoding for dict data

        Returns:
            Formatted SSE event string
        """
        lines = []

        # Add event type
        lines.append(f'event: {event_type}')

        # Add event ID if provided
        if event_id:
            lines.append(f'id: {event_id}')

        # Add retry interval if provided
        if retry:
            lines.append(f'retry: {retry}')

        # Encode and add data
        if isinstance(data, dict):
            encoded_data = SSEMessageCodec.encode_message(data=data, use_binary=use_binary)
            if isinstance(encoded_data, bytes):
                # For binary data over SSE, use base64 encoding as fallback
                # (HTTP/2 native binary support is ideal, but this ensures compatibility)
                encoded_data = base64.b64encode(encoded_data).decode('utf-8')
                lines.append(f'data: binary:{encoded_data}')
            else:
                # Text data can be multiline
                for line in str(encoded_data).split('\n'):
                    lines.append(f'data: {line}')
        else:
            # String or bytes data
            data_str = data.decode('utf-8') if isinstance(data, bytes) else str(data)
            for line in data_str.split('\n'):
                lines.append(f'data: {line}')

        # SSE events end with double newline
        lines.append('')
        lines.append('')

        return '\n'.join(lines)

    @staticmethod
    def create_heartbeat_event() -> str:
        """Create a heartbeat SSE event"""
        return SSEMessageCodec.format_sse_event(
            event_type=SSEConfig.EventType.HEARTBEAT,
            data={'timestamp': 'heartbeat'},
            use_binary=False,  # Keep heartbeats as simple text
        )

    @staticmethod
    def create_connection_event(user_id: int, event_id: int) -> str:
        """Create a connection confirmation SSE event"""
        return SSEMessageCodec.format_sse_event(
            event_type=SSEConfig.EventType.CONNECTED,
            data={
                'user_id': user_id,
                'event_id': event_id,
                'message': 'Connected to ticket updates',
            },
            use_binary=False,
        )

    @staticmethod
    def create_error_event(error_message: str, error_code: Optional[str] = None) -> str:
        """Create an error SSE event"""
        error_data = {'message': error_message}
        if error_code:
            error_data['code'] = error_code

        return SSEMessageCodec.format_sse_event(
            event_type=SSEConfig.EventType.ERROR, data=error_data, use_binary=False
        )

    @staticmethod
    def create_ticket_event(
        *, event_id: int, ticket_data: Dict[str, Any], event_type: str, use_binary: bool = True
    ) -> str:
        """Create a ticket update SSE event"""
        return SSEMessageCodec.format_sse_event(
            event_type=event_type,
            data={
                'event_id': event_id,
                'ticket_data': ticket_data,
                'timestamp': 'now',  # Could use actual timestamp
            },
            use_binary=use_binary,
        )

    @staticmethod
    def create_subsection_event(
        *,
        event_id: int,
        section: str,
        subsection: int,
        event_type: str,
        data: Dict[str, Any],
        use_binary: bool = True,
    ) -> str:
        """Create a subsection-specific SSE event"""
        event_data = {'event_id': event_id, 'section': section, 'subsection': subsection, **data}

        return SSEMessageCodec.format_sse_event(
            event_type=event_type, data=event_data, use_binary=use_binary
        )
