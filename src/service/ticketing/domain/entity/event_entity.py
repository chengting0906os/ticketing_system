from datetime import datetime
from typing import Dict, Optional

import attrs

from src.service.ticketing.domain.enum.event_status import EventStatus


def _validate_non_empty_string(instance: object, attribute: attrs.Attribute, value: str) -> None:
    if not value or not value.strip():
        raise ValueError(f'Event {attribute.name} cannot be empty')


@attrs.define
class EventEntity:
    name: str = attrs.field(validator=_validate_non_empty_string)
    description: str = attrs.field(validator=_validate_non_empty_string)
    seller_id: int
    venue_name: str = attrs.field(validator=_validate_non_empty_string)
    seating_config: Dict
    is_active: bool = True
    status: EventStatus = EventStatus.AVAILABLE
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    stats: Optional[Dict] = None
