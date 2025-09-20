"""
SSE Connection Manager

Manages Server-Sent Events connections with user metadata and filtering.
"""

import asyncio
from collections import defaultdict
from typing import Any, Dict, List, Set

from fastapi import Request
from loguru import logger

from src.shared.sse.sse_config import SSEConfig


class SSEConnection:
    """Represents an SSE connection with metadata"""

    def __init__(self, request: Request, event_id: int, user_metadata: Dict[str, Any]):
        self.request = request
        self.event_id = event_id
        self.user_metadata = user_metadata
        self.subscribed_sections: Set[str] = set()
        self.last_ping = asyncio.get_event_loop().time()
        self.is_active = True

    @property
    def user_id(self) -> int:
        return self.user_metadata.get('user_id', 0)

    @property
    def user_role(self) -> str:
        return self.user_metadata.get('role', 'unknown')


class SSEConnectionManager:
    """Manages SSE connections with event-based grouping and filtering"""

    def __init__(self):
        # event_id -> List[SSEConnection]
        self.connections: Dict[int, List[SSEConnection]] = defaultdict(list)
        self._connection_lock = asyncio.Lock()

    async def add_connection(
        self, request: Request, event_id: int, user_metadata: Dict[str, Any]
    ) -> SSEConnection:
        """Add a new SSE connection"""
        async with self._connection_lock:
            # Check connection limit per event
            if len(self.connections[event_id]) >= SSEConfig.MAX_CONNECTIONS_PER_EVENT:
                raise ValueError('Connection limit exceeded for this event')

            connection = SSEConnection(request, event_id, user_metadata)
            self.connections[event_id].append(connection)

            logger.info(
                f'SSE connection added: event_id={event_id}, '
                f'user_id={connection.user_id}, total_connections={len(self.connections[event_id])}'
            )

            return connection

    async def remove_connection(self, connection: SSEConnection) -> None:
        """Remove an SSE connection"""
        async with self._connection_lock:
            event_connections = self.connections.get(connection.event_id, [])
            if connection in event_connections:
                event_connections.remove(connection)
                connection.is_active = False

                logger.info(
                    f'SSE connection removed: event_id={connection.event_id}, '
                    f'user_id={connection.user_id}, remaining_connections={len(event_connections)}'
                )

                # Clean up empty event groups
                if not event_connections:
                    del self.connections[connection.event_id]

    async def get_connections_for_event(self, event_id: int) -> List[SSEConnection]:
        """Get all active connections for an event"""
        async with self._connection_lock:
            return [conn for conn in self.connections.get(event_id, []) if conn.is_active]

    async def get_connections_for_subsection(
        self, event_id: int, section: str, subsection: int
    ) -> List[SSEConnection]:
        """Get connections subscribed to a specific subsection"""
        async with self._connection_lock:
            subsection_key = f'{section}-{subsection}'
            return [
                conn
                for conn in self.connections.get(event_id, [])
                if conn.is_active and subsection_key in conn.subscribed_sections
            ]

    async def subscribe_to_section(
        self, connection: SSEConnection, section: str, subsection: int
    ) -> None:
        """Subscribe a connection to section updates"""
        subsection_key = f'{section}-{subsection}'
        connection.subscribed_sections.add(subsection_key)

        logger.debug(
            f'Connection subscribed to section: user_id={connection.user_id}, '
            f'section={subsection_key}, total_subscriptions={len(connection.subscribed_sections)}'
        )

    async def unsubscribe_from_section(
        self, connection: SSEConnection, section: str, subsection: int
    ) -> None:
        """Unsubscribe a connection from section updates"""
        subsection_key = f'{section}-{subsection}'
        connection.subscribed_sections.discard(subsection_key)

        logger.debug(
            f'Connection unsubscribed from section: user_id={connection.user_id}, '
            f'section={subsection_key}, remaining_subscriptions={len(connection.subscribed_sections)}'
        )

    async def update_heartbeat(self, connection: SSEConnection) -> None:
        """Update the last heartbeat time for a connection"""
        connection.last_ping = asyncio.get_event_loop().time()

    async def cleanup_stale_connections(self) -> None:
        """Remove connections that haven't sent heartbeat recently"""
        current_time = asyncio.get_event_loop().time()
        timeout = SSEConfig.DEFAULT_CONNECTION_TIMEOUT

        async with self._connection_lock:
            for event_id in list(self.connections.keys()):
                active_connections = []
                for conn in self.connections[event_id]:
                    if conn.is_active and (current_time - conn.last_ping) < timeout:
                        active_connections.append(conn)
                    else:
                        conn.is_active = False
                        logger.info(f'Cleaned up stale SSE connection: user_id={conn.user_id}')

                if active_connections:
                    self.connections[event_id] = active_connections
                else:
                    del self.connections[event_id]

    def get_connection_count(self, event_id: int) -> int:
        """Get the number of active connections for an event"""
        return len([conn for conn in self.connections.get(event_id, []) if conn.is_active])

    def get_total_connection_count(self) -> int:
        """Get the total number of active connections across all events"""
        return sum(
            len([conn for conn in connections if conn.is_active])
            for connections in self.connections.values()
        )


# Global instance
sse_connection_manager = SSEConnectionManager()
