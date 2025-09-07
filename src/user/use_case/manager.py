"""User manager for FastAPI Users integration."""

from typing import Optional

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, IntegerIDMixin

from src.shared.logging.loguru_io import Logger
from src.shared.config import settings
from src.user.domain.user_model import User
from src.user.infra.get_user_db import get_user_db


class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    """User manager for FastAPI Users."""
    
    reset_password_token_secret = settings.RESET_PASSWORD_TOKEN_SECRET
    verification_token_secret = settings.VERIFICATION_TOKEN_SECRET
    

    @Logger.io
    async def on_after_register(self, user: User, request: Optional[Request] = None):
        """Actions after user registration."""
        print(f'User {user.email} has registered.')
    
    # No need to override create() anymore - parent class handles email uniqueness

async def get_user_manager(user_db=Depends(get_user_db)):
    """Get user manager."""
    yield UserManager(user_db=user_db)
