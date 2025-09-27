from fastapi import Depends

from src.shared.exception.exceptions import ForbiddenError
from src.shared.logging.loguru_io import Logger
from src.shared_kernel.user.domain.user_entity import UserEntity, UserRole
from src.shared_kernel.user.port.user_controller import get_current_user as get_user_from_controller


class RoleAuthStrategy:
    @staticmethod
    def can_create_event(user: UserEntity) -> bool:
        return user.role == UserRole.SELLER

    @staticmethod
    def can_create_booking(user: UserEntity) -> bool:
        return user.role == UserRole.BUYER

    @staticmethod
    def is_buyer(user: UserEntity) -> bool:
        return user.role == UserRole.BUYER

    @staticmethod
    def is_seller(user: UserEntity) -> bool:
        return user.role == UserRole.SELLER


@Logger.io
def get_current_user(current_user: UserEntity = Depends(get_user_from_controller)) -> UserEntity:
    return current_user


@Logger.io
def require_buyer(current_user: UserEntity = Depends(get_user_from_controller)) -> UserEntity:
    if not RoleAuthStrategy.can_create_booking(current_user):
        raise ForbiddenError('Only buyers can perform this action')
    return current_user


@Logger.io
def require_seller(current_user: UserEntity = Depends(get_user_from_controller)) -> UserEntity:
    if not RoleAuthStrategy.can_create_event(current_user):
        raise ForbiddenError('Only sellers can perform this action')
    return current_user


@Logger.io
def require_buyer_or_seller(
    current_user: UserEntity = Depends(get_user_from_controller),
) -> UserEntity:
    if current_user.role not in [UserRole.BUYER, UserRole.SELLER]:
        raise ForbiddenError("You don't have permission to perform this action")
    return current_user
