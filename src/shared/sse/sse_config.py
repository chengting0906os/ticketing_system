"""
Server-Sent Events (SSE) Configuration
"""

from typing import Final


class SSEConfig:
    """Configuration for Server-Sent Events"""

    # Default heartbeat interval (seconds)
    DEFAULT_HEARTBEAT_INTERVAL: Final[float] = 30.0

    # Connection timeout (seconds)
    DEFAULT_CONNECTION_TIMEOUT: Final[float] = 300.0

    # Maximum number of connections per event
    MAX_CONNECTIONS_PER_EVENT: Final[int] = 1000

    # Content types
    CONTENT_TYPE_TEXT: Final[str] = 'text/plain; charset=utf-8'
    CONTENT_TYPE_BINARY: Final[str] = 'application/msgpack'

    # Event types
    class EventType:
        CONNECTED: Final[str] = 'connected'
        HEARTBEAT: Final[str] = 'heartbeat'
        TICKET_RESERVED: Final[str] = 'ticket_reserved'
        TICKET_AVAILABLE: Final[str] = 'ticket_available'
        SUBSECTION_UPDATE: Final[str] = 'subsection_update'
        EVENT_UPDATE: Final[str] = 'event_update'
        ERROR: Final[str] = 'error'


class SSEErrorMessages:
    """Standard SSE error messages"""

    AUTHENTICATION_FAILED: Final[str] = 'Authentication failed'
    INVALID_TOKEN: Final[str] = 'Invalid authentication token'
    MISSING_TOKEN: Final[str] = 'Missing authentication token'
    FORBIDDEN: Final[str] = 'Access forbidden'
    CONNECTION_LIMIT_EXCEEDED: Final[str] = 'Connection limit exceeded'
    INTERNAL_ERROR: Final[str] = 'Internal server error'
