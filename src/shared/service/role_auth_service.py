from fastapi import Depends

from src.shared.auth.current_user_info import CurrentUserInfo
from src.shared.exception.exceptions import ForbiddenError
from src.shared.logging.loguru_io import Logger
from src.user.domain.user_entity import UserEntity, UserRole
from src.user.port.user_controller import get_current_user


class RoleAuthService:
    @staticmethod
    @Logger.io
    def can_create_event(user: UserEntity) -> bool:
        return user.role == UserRole.SELLER

    @staticmethod
    @Logger.io
    def can_create_booking(user: UserEntity) -> bool:
        return user.role == UserRole.BUYER

    @staticmethod
    @Logger.io
    def is_buyer(user: UserEntity) -> bool:
        return user.role == UserRole.BUYER

    @staticmethod
    @Logger.io
    def is_seller(user: UserEntity) -> bool:
        return user.role == UserRole.SELLER


@Logger.io
def get_current_user_legacy(current_user: UserEntity = Depends(get_current_user)) -> UserEntity:
    return current_user


@Logger.io
def require_buyer(current_user: UserEntity = Depends(get_current_user)) -> UserEntity:
    if not RoleAuthService.can_create_booking(current_user):
        raise ForbiddenError('Only buyers can perform this action')
    return current_user


@Logger.io
def require_seller(current_user: UserEntity = Depends(get_current_user)) -> UserEntity:
    if not RoleAuthService.can_create_event(current_user):
        raise ForbiddenError('Only sellers can perform this action')
    return current_user


@Logger.io
def require_buyer_or_seller(current_user: UserEntity = Depends(get_current_user)) -> UserEntity:
    if current_user.role not in [UserRole.BUYER, UserRole.SELLER]:
        raise ForbiddenError("You don't have permission to perform this action")
    return current_user


# Domain-boundary-safe functions that return abstract user info
@Logger.io
def get_current_user_info(current_user: UserEntity = Depends(get_current_user)) -> CurrentUserInfo:
    """Get current user info without exposing User domain entity"""
    if current_user.id is None:
        raise ForbiddenError('User ID is missing')
    return CurrentUserInfo(user_id=current_user.id, role=current_user.role)


@Logger.io
def require_buyer_info(current_user: UserEntity = Depends(require_buyer)) -> CurrentUserInfo:
    """Get buyer user info without exposing User domain entity"""
    if current_user.id is None:
        raise ForbiddenError('User ID is missing')
    return CurrentUserInfo(user_id=current_user.id, role=current_user.role)


@Logger.io
def require_seller_info(current_user: UserEntity = Depends(require_seller)) -> CurrentUserInfo:
    """Get seller user info without exposing User domain entity"""
    if current_user.id is None:
        raise ForbiddenError('User ID is missing')
    return CurrentUserInfo(user_id=current_user.id, role=current_user.role)
