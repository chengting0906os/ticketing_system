"""Product domain errors."""

from enum import Enum


class ProductErrorMessage(Enum):
    PRICE_MUST_BE_POSITIVE = "Price must be positive"
    NAME_REQUIRED = "Product name is required"
    DESCRIPTION_REQUIRED = "Product description is required"
    INVALID_SELLER = "Invalid seller ID"
    PRODUCT_NOT_FOUND = "Product not found"


class ProductDomainError(Exception):    
    def __init__(self, message: ProductErrorMessage):
        self.error_message = message
        super().__init__(message.value)


class InvalidPriceError(ProductDomainError):
    def __init__(self):
        super().__init__(ProductErrorMessage.PRICE_MUST_BE_POSITIVE)


class InvalidProductDataError(ProductDomainError):
    pass
