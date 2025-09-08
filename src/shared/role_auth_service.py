"""Authentication domain service."""

from src.shared.logging.loguru_io import Logger
from src.user.domain.user_entity import UserRole
from src.user.domain.user_model import User


class RoleAuthService:
    @staticmethod
    @Logger.io
    def can_create_product(user: User) -> bool:
        return user.role == UserRole.SELLER

    @staticmethod
    @Logger.io
    def can_create_order(user: User) -> bool:
        return user.role == UserRole.BUYER

    @staticmethod
    @Logger.io
    def can_manage_own_products(user: User, seller_id: int) -> bool:
        return user.role == UserRole.SELLER and user.id == seller_id

    @staticmethod
    @Logger.io
    def can_manage_own_orders(user: User, buyer_id: int) -> bool:
        return user.role == UserRole.BUYER and user.id == buyer_id
