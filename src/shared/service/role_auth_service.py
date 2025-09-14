from fastapi import Depends

from src.shared.exception.exceptions import ForbiddenError
from src.shared.logging.loguru_io import Logger
from src.shared.service.jwt_auth_service import current_active_user
from src.user.domain.user_entity import UserRole
from src.user.domain.user_model import User


class RoleAuthService:
    @staticmethod
    @Logger.io
    def can_create_event(user: User) -> bool:
        return user.role == UserRole.SELLER

    @staticmethod
    @Logger.io
    def can_create_booking(user: User) -> bool:
        return user.role == UserRole.BUYER


@Logger.io
def get_current_user(current_user: User = Depends(current_active_user)) -> User:
    return current_user


@Logger.io
def require_buyer(current_user: User = Depends(get_current_user)) -> User:
    if not RoleAuthService.can_create_booking(current_user):
        raise ForbiddenError('Only buyers can perform this action')
    return current_user


@Logger.io
def require_seller(current_user: User = Depends(get_current_user)) -> User:
    if not RoleAuthService.can_create_event(current_user):
        raise ForbiddenError('Only sellers can perform this action')
    return current_user


@Logger.io
def require_buyer_or_seller(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in [UserRole.BUYER, UserRole.SELLER]:
        raise ForbiddenError("You don't have permission to perform this action")
    return current_user
