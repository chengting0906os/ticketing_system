from enum import Enum
from typing import Dict, Optional

import attrs

from src.shared.logging.loguru_io import Logger


class EventStatus(str, Enum):
    AVAILABLE = 'available'
    SOLD_OUT = 'sold_out'
    ENDED = 'ended'


# Validation logic moved to shared validators module


@attrs.define
class Event:
    name: str
    description: str
    seller_id: int
    venue_name: str
    seating_config: Dict
    is_active: bool = True
    status: EventStatus = EventStatus.AVAILABLE
    id: Optional[int] = None

    @classmethod
    @Logger.io
    def create_event_and_tickets(
        cls,
        *,
        name: str,
        description: str,
        seller_id: int,
        venue_name: str,
        seating_config: Dict,
        is_active: bool = True,
    ) -> 'Event':
        return cls(
            name=name,
            description=description,
            seller_id=seller_id,
            venue_name=venue_name,
            seating_config=seating_config,
            is_active=is_active,
            status=EventStatus.AVAILABLE,
            id=None,
        )
