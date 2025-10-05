"""
User Management Use Cases (Use Case Layer)
"""

from dependency_injector.wiring import Provide, inject
from fastapi import Depends

from src.service.ticketing.domain.entity.user_entity import UserEntity, UserRole
from src.service.ticketing.app.interface.i_user_repo import UserRepo
from src.service.ticketing.driven_adapter.security.bcrypt_password_hasher import (
    BcryptPasswordHasher,
)


class UserUseCase:
    """User management use case class with proper dependency injection"""

    def __init__(self, user_repo: UserRepo):
        self.user_repo = user_repo

    @classmethod
    @inject
    def depends(cls, user_repo: UserRepo = Depends(Provide['user_repo'])):
        return cls(user_repo=user_repo)

    async def create_user(
        self,
        email: str,
        password: str,
        name: str,
        role: UserRole = UserRole.BUYER,
    ) -> UserEntity:
        UserEntity.validate_role(role)
        user_entity = UserEntity(
            email=email, name=name, role=role, is_active=True, is_superuser=False, is_verified=False
        )

        password_hasher = BcryptPasswordHasher()
        user_entity.set_password(password, password_hasher)
        return await self.user_repo.create(user_entity)

    async def get_user_by_id(self, user_id: int) -> UserEntity | None:
        return await self.user_repo.get_by_id(user_id)


# Note: For global instance, use the DI container in your application setup
