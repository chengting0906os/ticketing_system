"""
SSE Event Type Enum - Domain Value Object

This enum defines the types of Server-Sent Events for real-time updates.
"""

from enum import Enum


class SseEventType(Enum):
    """SSE event type enumeration for real-time streaming"""

    INITIAL_STATUS = 'initial_status'
    STATUS_UPDATE = 'status_update'
