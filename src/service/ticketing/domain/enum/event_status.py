"""
Shared Event Status Enum - Domain Value Object

This enum is shared across bounded contexts to maintain consistency
in event status representation throughout the system.
"""

from enum import Enum


class EventStatus(Enum):
    """Event status enumeration shared across domains"""

    DRAFT = 'draft'
    AVAILABLE = 'available'
    SOLD_OUT = 'sold_out'
    CANCELLED = 'cancelled'
    COMPLETED = 'completed'
    ENDED = 'ended'  # Event has ended (time-based)
