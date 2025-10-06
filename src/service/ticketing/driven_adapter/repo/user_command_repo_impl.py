from typing import AsyncContextManager, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_user_command_repo import IUserCommandRepo
from src.service.ticketing.domain.entity.user_entity import UserEntity, UserRole
from src.service.ticketing.driven_adapter.model.user_model import UserModel


class UserCommandRepoImpl(IUserCommandRepo):
    def __init__(self, session_factory: Callable[..., AsyncContextManager[AsyncSession]]):
        self.session_factory = session_factory

    @Logger.io
    async def create(self, user_entity: UserEntity) -> UserEntity:
        async with self.session_factory() as session:
            user_model = UserModel(
                email=user_entity.email,
                hashed_password=user_entity.hashed_password,
                name=user_entity.name,
                role=user_entity.role,
                is_active=user_entity.is_active,
                is_superuser=user_entity.is_superuser,
                is_verified=user_entity.is_verified,
            )

            session.add(user_model)
            await session.commit()
            await session.refresh(user_model)

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
