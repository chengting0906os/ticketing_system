"""Shared dependencies for authentication and authorization."""

from typing import Optional

from fastapi import Depends, HTTPException, status

from src.shared.logging.loguru_io import Logger
from src.shared.jwt_auth_service import current_active_user
from src.shared.role_auth_service import RoleAuthService
from src.user.domain.user_entity import UserRole
from src.user.domain.user_model import User


@Logger.io
def get_current_user(current_user: User = Depends(current_active_user)) -> User:
    return current_user


@Logger.io
def require_buyer(current_user: User = Depends(get_current_user)) -> User:
    if not RoleAuthService.can_create_order(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail='Only buyers can perform this action'
        )
    return current_user


@Logger.io
def require_seller(current_user: User = Depends(get_current_user)) -> User:
    if not RoleAuthService.can_create_product(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail='Only sellers can perform this action'
        )
    return current_user


@Logger.io
def require_buyer_or_seller(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in [UserRole.BUYER, UserRole.SELLER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to perform this action",
        )
    return current_user


class CurrentUserDep:
    def __init__(self, required_role: Optional[UserRole] = None):
        self.required_role = required_role

    @Logger.io
    def __call__(self, current_user: User = Depends(current_active_user)) -> User:
        if self.required_role and current_user.role != self.required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f'Only {self.required_role} can perform this action',
            )
        return current_user
