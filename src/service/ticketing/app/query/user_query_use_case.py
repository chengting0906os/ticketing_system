"""
User Management Use Cases (Use Case Layer)
"""

from uuid import UUID

from src.service.ticketing.domain.entity.user_entity import UserEntity, UserRole
from src.service.ticketing.app.interface.i_user_command_repo import IUserCommandRepo
from src.service.ticketing.app.interface.i_user_query_repo import IUserQueryRepo
from src.service.ticketing.driven_adapter.security.bcrypt_password_hasher import (
    BcryptPasswordHasher,
)


class UserUseCase:
    """User management use case class with proper dependency injection (CQRS)"""

    def __init__(
        self,
        user_command_repo: IUserCommandRepo | None = None,
        user_query_repo: IUserQueryRepo | None = None,
    ):
        self.user_command_repo = user_command_repo
        self.user_query_repo = user_query_repo

    async def create_user(
        self,
        email: str,
        password: str,
        name: str,
        role: UserRole = UserRole.BUYER,
    ) -> UserEntity:
        if not self.user_command_repo:
            raise RuntimeError('UserCommandRepo not injected')

        UserEntity.validate_role(role)
        user_entity = UserEntity(
            email=email, name=name, role=role, is_active=True, is_superuser=False, is_verified=False
        )

        password_hasher = BcryptPasswordHasher()
        user_entity.set_password(password, password_hasher)
        return await self.user_command_repo.create(user_entity)

    async def get_user_by_id(self, user_id: UUID) -> UserEntity | None:
        if not self.user_query_repo:
            raise RuntimeError('UserQueryRepo not injected')

        return await self.user_query_repo.get_by_id(user_id)


# Note: For global instance, use the DI container in your application setup
