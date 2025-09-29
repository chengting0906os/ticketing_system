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
