"""Event entity."""

from enum import Enum
from typing import Dict, Optional

import attrs

from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger


class EventStatus(str, Enum):
    AVAILABLE = 'available'
    RESERVED = 'reserved'
    SOLD = 'sold'


@Logger.io
def validate_positive_price(instance, attribute, value):
    # value = -1
    if value < 0:
        raise DomainError('Price must be positive')


@Logger.io
def validate_name(instance, attribute, value):
    if not value or not value.strip():
        raise DomainError('Event name is required')


@Logger.io
def validate_description(instance, attribute, value):
    if not value or not value.strip():
        raise DomainError('Event description is required')


@Logger.io
def validate_venue_name(instance, attribute, value):
    if not value or not value.strip():
        raise DomainError('Venue name is required')


@Logger.io
def validate_seating_config(instance, attribute, value):
    if not value:
        raise DomainError('Seating config is required')


@attrs.define
class Event:
    name: str = attrs.field(validator=[attrs.validators.instance_of(str), validate_name])
    description: str = attrs.field(
        validator=[attrs.validators.instance_of(str), validate_description]
    )
    price: int = attrs.field(validator=[attrs.validators.instance_of(int), validate_positive_price])
    seller_id: int = attrs.field(validator=attrs.validators.instance_of(int))
    venue_name: str = attrs.field(
        validator=[attrs.validators.instance_of(str), validate_venue_name]
    )
    seating_config: Dict = attrs.field(validator=[validate_seating_config])
    is_active: bool = attrs.field(default=True, validator=attrs.validators.instance_of(bool))
    status: EventStatus = attrs.field(
        default=EventStatus.AVAILABLE, validator=attrs.validators.instance_of(EventStatus)
    )
    id: Optional[int] = None

    @classmethod
    @Logger.io
    def create(
        cls,
        name: str,
        description: str,
        price: int,
        seller_id: int,
        venue_name: str,
        seating_config: Dict,
        is_active: bool = True,
    ) -> 'Event':
        return cls(
            name=name,
            description=description,
            price=price,
            seller_id=seller_id,
            venue_name=venue_name,
            seating_config=seating_config,
            is_active=is_active,
            status=EventStatus.AVAILABLE,
            id=None,
        )
