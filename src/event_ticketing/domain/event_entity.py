from enum import Enum
from typing import Dict, Optional

import attrs

from src.shared.domain.validators import StringValidators, StructuredDataValidators
from src.shared.logging.loguru_io import Logger


class EventStatus(str, Enum):
    AVAILABLE = 'available'
    SOLD_OUT = 'sold_out'
    ENDED = 'ended'


# Validation logic moved to shared validators module


@attrs.define
class Event:
    name: str = attrs.field(
        validator=[attrs.validators.instance_of(str), StringValidators.validate_name]
    )
    description: str = attrs.field(
        validator=[attrs.validators.instance_of(str), StringValidators.validate_description]
    )
    seller_id: int = attrs.field(validator=attrs.validators.instance_of(int))
    venue_name: str = attrs.field(
        validator=[attrs.validators.instance_of(str), StringValidators.validate_venue_name]
    )
    seating_config: Dict = attrs.field(validator=[StructuredDataValidators.validate_seating_config])
    is_active: bool = attrs.field(default=True, validator=attrs.validators.instance_of(bool))
    status: EventStatus = attrs.field(
        default=EventStatus.AVAILABLE, validator=attrs.validators.instance_of(EventStatus)
    )
    id: Optional[int] = None

    @classmethod
    @Logger.io
    def create(
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
