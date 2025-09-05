"""Product entity."""

from enum import Enum
from typing import Optional

import attrs

from src.product.domain.errors import (
    InvalidPriceError,
    InvalidProductDataError,
    ProductErrorMessage,
)


class ProductStatus(str, Enum):    
    AVAILABLE = 'available'
    RESERVED = 'reserved'
    SOLD = 'sold'


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
    seller_id: int = attrs.field(validator=attrs.validators.instance_of(int))
    is_active: bool = attrs.field(default=True, validator=attrs.validators.instance_of(bool))
    status: ProductStatus = attrs.field(default=ProductStatus.AVAILABLE, validator=attrs.validators.instance_of(ProductStatus))
    id: Optional[int] = None
    
    @classmethod
    def create(cls, name: str, description: str, price: int, seller_id: int, is_active:bool) -> 'Product':
        return cls(
            name=name,
            description=description,
            price=price,
            seller_id=seller_id,
            is_active=is_active,
            status=ProductStatus.AVAILABLE,
            id=None
        )
