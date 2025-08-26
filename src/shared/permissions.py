"""User permissions - FastAPI dependencies."""

from fastapi import Depends, HTTPException, status

from src.user.domain.user_model import User, UserRole
from src.user.infra.auth import current_active_user


async def is_organizer(user: User = Depends(current_active_user)) -> User:
    """Check if user is an organizer."""
    if user.role != UserRole.ORGANIZER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only organizers can access this resource'
        )
    return user


async def is_customer(user: User = Depends(current_active_user)) -> User:
    """Check if user is a customer."""
    if user.role != UserRole.CUSTOMER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only customers can access this resource'
        )
    return user
