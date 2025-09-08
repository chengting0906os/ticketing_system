"""User repository implementation."""

from fastapi import Depends
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.config.db_setting import get_async_session
from src.user.domain.user_model import User


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    """Get user database."""
    yield SQLAlchemyUserDatabase(session, User)
