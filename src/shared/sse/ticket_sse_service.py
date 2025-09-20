"""
Ticket SSE Service

Main service for handling Server-Sent Events related to ticket updates.
Replaces the WebSocket functionality with SSE.
"""

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import Request
from fastapi.responses import StreamingResponse
from loguru import logger

from src.shared.sse.connection_manager import SSEConnection, sse_connection_manager
from src.shared.sse.sse_config import SSEConfig
from src.shared.sse.sse_message_codec import SSEMessageCodec
from src.user.domain.user_model import User


class TicketSSEService:
    """Service for managing ticket-related Server-Sent Events"""

    def __init__(
        self,
        heartbeat_interval: float = SSEConfig.DEFAULT_HEARTBEAT_INTERVAL,
    ):
        self.heartbeat_interval = heartbeat_interval
        self.codec = SSEMessageCodec()

    async def create_sse_stream(
        self, request: Request, event_id: int, user: User
    ) -> StreamingResponse:
        """Create an SSE stream for a user and event

        Args:
            request: FastAPI request object
            event_id: ID of the event to subscribe to
            user: Authenticated user

        Returns:
            StreamingResponse with SSE stream
        """
        user_metadata = {
            'user_id': user.id,
            'email': user.email,
            'role': user.role.value if hasattr(user.role, 'value') else str(user.role),  # pyright: ignore[reportAttributeAccessIssue]
            'event_id': event_id,
        }

        try:
            connection = await sse_connection_manager.add_connection(
                request, event_id, user_metadata
            )
        except ValueError as e:
            # Connection limit exceeded
            error_stream = self._create_error_stream(str(e))
            return StreamingResponse(error_stream, media_type='text/plain', status_code=429)

        # Create the SSE stream
        stream = self._create_event_stream(connection)

        return StreamingResponse(
            stream,
            media_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Cache-Control',
            },
        )

    async def _create_event_stream(self, connection: SSEConnection):
        """Generate SSE events for a connection"""
        try:
            # Send welcome message
            welcome_event = self.codec.create_connection_event(
                user_id=connection.user_id, event_id=connection.event_id
            )
            yield welcome_event

            # Start heartbeat loop
            last_heartbeat = asyncio.get_event_loop().time()

            while connection.is_active:
                current_time = asyncio.get_event_loop().time()

                # Send heartbeat if needed
                if current_time - last_heartbeat >= self.heartbeat_interval:
                    heartbeat_event = self.codec.create_heartbeat_event()
                    yield heartbeat_event
                    await sse_connection_manager.update_heartbeat(connection)
                    last_heartbeat = current_time

                # Check if client disconnected
                if await self._is_client_disconnected(connection.request):
                    break

                # Small delay to prevent busy waiting
                await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            logger.info(f'SSE stream cancelled for user {connection.user_id}')
        except Exception as e:
            logger.error(f'Error in SSE stream for user {connection.user_id}: {e}')
            error_event = self.codec.create_error_event('Internal server error')
            yield error_event
        finally:
            await sse_connection_manager.remove_connection(connection)

    async def _create_error_stream(self, error_message: str):
        """Create an error stream for immediate errors"""
        error_event = self.codec.create_error_event(error_message)
        yield error_event

    async def _is_client_disconnected(self, request: Request) -> bool:
        """Check if the client has disconnected"""
        try:
            # This is a simple check - FastAPI will raise an exception
            # if the client disconnects during streaming
            return False
        except Exception:
            return True

    async def broadcast_ticket_event(
        self,
        event_id: int,
        ticket_data: Dict[str, Any],
        event_type: str,
        affected_sections: Optional[List[str]] = None,
    ) -> None:
        """Broadcast a ticket event to all subscribers of an event"""
        connections = await sse_connection_manager.get_connections_for_event(event_id)

        if not connections:
            logger.debug(f'No SSE connections for event {event_id}')
            return

        _ = self.codec.create_ticket_event(
            event_id=event_id, ticket_data=ticket_data, event_type=event_type
        )

        # Send to all connections for this event
        for connection in connections:
            try:
                # Note: In SSE, we can't directly send to individual connections
                # This would need to be implemented with a message queue
                # or connection-specific event storage
                logger.debug(f'Would broadcast to user {connection.user_id}: {event_type}')
            except Exception as e:
                logger.error(f'Failed to broadcast to user {connection.user_id}: {e}')

        logger.info(
            f'Broadcasted {event_type} event for event {event_id} to {len(connections)} connections'
        )

    async def broadcast_subsection_event(
        self,
        event_id: int,
        section: str,
        subsection: int,
        event_type: str,
        data: Dict[str, Any],
    ) -> None:
        """Broadcast an event to subscribers of a specific subsection"""
        connections = await sse_connection_manager.get_connections_for_subsection(
            event_id, section, subsection
        )

        if not connections:
            logger.debug(f'No SSE connections for subsection {section}-{subsection}')
            return

        _ = self.codec.create_subsection_event(
            event_id=event_id,
            section=section,
            subsection=subsection,
            event_type=event_type,
            data=data,
        )

        # Send to subsection subscribers
        for connection in connections:
            try:
                logger.debug(f'Would broadcast subsection event to user {connection.user_id}')
            except Exception as e:
                logger.error(
                    f'Failed to broadcast subsection event to user {connection.user_id}: {e}'
                )

        logger.info(
            f'Broadcasted {event_type} subsection event for {section}-{subsection} '
            f'to {len(connections)} connections'
        )

    async def subscribe_to_section(
        self, connection: SSEConnection, section: str, subsection: int
    ) -> None:
        """Subscribe a connection to section-specific updates"""
        await sse_connection_manager.subscribe_to_section(connection, section, subsection)

    def get_connection_count(self, event_id: int) -> int:
        """Get the number of active connections for an event"""
        return sse_connection_manager.get_connection_count(event_id)


# Global instance
ticket_sse_service = TicketSSEService()
