"""User models."""

from enum import Enum


class UserRole(str, Enum):
    SELLER = 'seller'
    BUYER = 'buyer'
