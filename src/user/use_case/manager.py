"""User manager for FastAPI Users integration."""
# https://fastapi-users.github.io/fastapi-users/10.1/configuration/user-manager/

from typing import Optional

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, IntegerIDMixin

from src.shared.config import settings
from src.shared.logging.loguru_io import Logger
from src.user.domain.user_model import User
from src.user.infra.get_user_db import get_user_db


class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    reset_password_token_secret = settings.RESET_PASSWORD_TOKEN_SECRET
    verification_token_secret = settings.VERIFICATION_TOKEN_SECRET

    @Logger.io
    async def on_after_register(self, user: User, request: Optional[Request] = None):
        """Hook called after successful user registration.

        Note:
            This method can be used to:
            - Send welcome emails
            - Create initial user settings
            - Trigger webhooks or notifications
        """
        pass

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        pass

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        pass


async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db=user_db)
