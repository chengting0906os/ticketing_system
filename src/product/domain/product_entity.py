"""Product entity."""

from typing import Optional
from uuid import UUID

import attrs

from src.product.domain.errors import (
    InvalidPriceError,
    InvalidProductDataError,
    ProductErrorMessage,
)


def validate_positive_price(instance, attribute, value):
    if value < 0:
        raise InvalidPriceError()


def validate_name(instance, attribute, value):
    if not value or not value.strip():
        raise InvalidProductDataError(ProductErrorMessage.NAME_REQUIRED)


def validate_description(instance, attribute, value):
    if not value or not value.strip():
        raise InvalidProductDataError(ProductErrorMessage.DESCRIPTION_REQUIRED)


@attrs.define
class Product:
    name: str = attrs.field(validator=[attrs.validators.instance_of(str), validate_name])
    description: str = attrs.field(validator=[attrs.validators.instance_of(str), validate_description])
    price: int = attrs.field(validator=[attrs.validators.instance_of(int), validate_positive_price])
    seller_id: UUID = attrs.field(validator=attrs.validators.instance_of(UUID))
    id: Optional[int] = None
    
    @classmethod
    def create(cls, name: str, description: str, price: int, seller_id: UUID) -> 'Product':
        return cls(
            name=name,
            description=description,
            price=price,
            seller_id=seller_id,
            id=None
        )
