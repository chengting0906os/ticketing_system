from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.logging.loguru_io import Logger
from src.shared_kernel.user.domain.user_command_repo import UserCommandRepo
from src.shared_kernel.user.domain.user_entity import UserEntity, UserRole
from src.shared_kernel.user.infra.user_model import UserModel


class UserCommandRepoImpl(UserCommandRepo):
    def __init__(self, session: AsyncSession):
        self.session = session

    @Logger.io
    async def create(self, user_entity: UserEntity) -> UserEntity:
        user_model = UserModel(
            email=user_entity.email,
            hashed_password=user_entity.hashed_password,
            name=user_entity.name,
            role=user_entity.role,
            is_active=user_entity.is_active,
            is_superuser=user_entity.is_superuser,
            is_verified=user_entity.is_verified,
        )

        self.session.add(user_model)
        await self.session.commit()
        await self.session.refresh(user_model)

        return self._model_to_entity(user_model)

    @Logger.io
    async def update(self, user_entity: UserEntity) -> UserEntity:
        result = await self.session.execute(select(UserModel).where(UserModel.id == user_entity.id))
        user_model = result.scalar_one_or_none()

        if not user_model:
            raise ValueError(f'User with id {user_entity.id} not found')

        user_model.email = user_entity.email
        user_model.name = user_entity.name
        user_model.hashed_password = user_entity.hashed_password
        user_model.role = user_entity.role
        user_model.is_active = user_entity.is_active
        user_model.is_superuser = user_entity.is_superuser
        user_model.is_verified = user_entity.is_verified

        await self.session.commit()
        await self.session.refresh(user_model)

        return self._model_to_entity(user_model)

    @Logger.io
    async def delete(self, user_id: int) -> bool:
        result = await self.session.execute(select(UserModel).where(UserModel.id == user_id))
        user_model = result.scalar_one_or_none()

        if not user_model:
            return False

        await self.session.delete(user_model)
        await self.session.commit()
        return True

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
