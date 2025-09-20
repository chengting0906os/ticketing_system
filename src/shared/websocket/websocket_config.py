"""WebSocket configuration constants and settings."""

from typing import Final


class WebSocketConfig:
    """Configuration constants for WebSocket service."""

    # Timing settings
    DEFAULT_PING_INTERVAL: Final[float] = 30.0
    DEFAULT_PING_TIMEOUT: Final[float] = 30.0

    # Business rules
    MAX_TICKETS_PER_BOOKING: Final[int] = 4
    MIN_TICKETS_PER_BOOKING: Final[int] = 1

    # Message types
    class MessageType:
        """WebSocket message type constants."""

        # Connection management
        CONNECTED: Final[str] = 'connected'
        PING: Final[str] = 'ping'
        PONG: Final[str] = 'pong'
        ERROR: Final[str] = 'error'

        # Subscription management
        SUBSCRIPTION_CONFIRMED: Final[str] = 'subscription_confirmed'
        STATUS_REQUESTED: Final[str] = 'status_requested'

        # Ticket events
        TICKET_RESERVED: Final[str] = 'ticket_reserved'
        TICKET_CANCELLED: Final[str] = 'ticket_cancelled'
        SUBSECTION_TICKETS_RESERVED: Final[str] = 'subsection_tickets_reserved'
        RESERVATION_SUMMARY: Final[str] = 'reservation_summary'

    class ActionType:
        """WebSocket action type constants."""

        SUBSCRIBE_SECTIONS: Final[str] = 'subscribe_sections'
        PING: Final[str] = 'ping'
        GET_CURRENT_STATUS: Final[str] = 'get_current_status'


class WebSocketErrorMessages:
    CONNECTION_METADATA_NOT_FOUND: Final[str] = 'Connection metadata not found'
    INVALID_MESSAGE_FORMAT: Final[str] = 'Invalid message format'
    SECTIONS_MUST_BE_LIST: Final[str] = 'Sections must be a list of strings'
    UNKNOWN_ACTION: Final[str] = 'Unknown action'
    USE_API_FOR_INITIAL_DATA: Final[str] = 'Use regular API endpoints for initial data load'
