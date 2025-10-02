from typing import AsyncContextManager, Callable, Optional

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.platform.logging.loguru_io import Logger
from src.shared_kernel.user.domain.user_entity import UserEntity, UserRole
from src.shared_kernel.user.domain.user_query_repo import UserQueryRepo
from src.shared_kernel.user.driven_adapter.bcrypt_password_hasher import BcryptPasswordHasher
from src.shared_kernel.user.driven_adapter.user_model import UserModel


class UserQueryRepoImpl(UserQueryRepo):
    def __init__(self, session_factory: Callable[..., AsyncContextManager[AsyncSession]]):
        self.session_factory = session_factory
        self.password_hasher = BcryptPasswordHasher()

    @Logger.io
    async def get_by_email(self, email: str) -> Optional[UserEntity]:
        async with self.session_factory() as session:
            result = await session.execute(select(UserModel).where(UserModel.email == email))
            user_model = result.scalar_one_or_none()

            if not user_model:
                return None

            return self._model_to_entity(user_model)

    @Logger.io
    async def get_by_id(self, user_id: int) -> Optional[UserEntity]:
        async with self.session_factory() as session:
            result = await session.execute(select(UserModel).where(UserModel.id == user_id))
            user_model = result.scalar_one_or_none()

            if not user_model:
                return None

            return self._model_to_entity(user_model)

    @Logger.io
    async def exists_by_email(self, email: str) -> bool:
        async with self.session_factory() as session:
            result = await session.execute(select(UserModel.id).where(UserModel.email == email))
            return result.scalar_one_or_none() is not None

    @Logger.io
    async def verify_password(self, email: str, plain_password: str) -> Optional[UserEntity]:
        async with self.session_factory() as session:
            result = await session.execute(select(UserModel).where(UserModel.email == email))
            user_model = result.scalar_one_or_none()

            if not user_model:
                return None

            # 使用 SecretStr 保護敏感密碼資料
            secret_password = SecretStr(plain_password)

            if not self.password_hasher.verify_password(
                plain_password=secret_password, hashed_password=user_model.hashed_password
            ):
                return None

            return self._model_to_entity(user_model)

    def _model_to_entity(self, user_model: UserModel) -> UserEntity:
        return UserEntity(
            id=user_model.id,
            email=user_model.email,
            name=user_model.name,
            role=UserRole(user_model.role),
            is_active=user_model.is_active,
            is_superuser=user_model.is_superuser,
            is_verified=user_model.is_verified,
            created_at=user_model.created_at,
        )
