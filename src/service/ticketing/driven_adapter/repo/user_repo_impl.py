"""
User Repository Implementation - Combines Command and Query operations
"""

from typing import AsyncContextManager, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.service.ticketing.domain.entity.user_entity import UserEntity
from src.service.ticketing.app.interface.i_user_repo import UserRepo
from src.service.ticketing.driven_adapter.repo.user_command_repo_impl import UserCommandRepoImpl
from src.service.ticketing.driven_adapter.repo.user_query_repo_impl import UserQueryRepoImpl


class UserRepoImpl(UserRepo):
    """
    Unified User Repository combining Command and Query operations

    This class delegates to specialized repositories for CQRS separation.
    """

    def __init__(self, session_factory: Callable[..., AsyncContextManager[AsyncSession]]):
        self.command_repo = UserCommandRepoImpl(session_factory)
        self.query_repo = UserQueryRepoImpl(session_factory)

    async def get_by_email(self, email: str) -> Optional[UserEntity]:
        return await self.query_repo.get_by_email(email)

    async def get_by_id(self, user_id: int) -> Optional[UserEntity]:
        return await self.query_repo.get_by_id(user_id)

    async def create(self, user_entity: UserEntity) -> UserEntity:
        return await self.command_repo.create(user_entity)

    async def exists_by_email(self, email: str) -> bool:
        return await self.query_repo.exists_by_email(email)

    async def verify_password(self, email: str, plain_password: str) -> Optional[UserEntity]:
        return await self.query_repo.verify_password(email, plain_password)
