import asyncio
from datetime import datetime, timezone
from uuid import UUID

from uuid_utils import uuid7

from src.platform.database.scylla_setting import get_scylla_session
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_user_command_repo import IUserCommandRepo
from src.service.ticketing.domain.entity.user_entity import UserEntity, UserRole


class UserCommandRepoScyllaImpl(IUserCommandRepo):
    """
    ScyllaDB User Command Repository

    No session_factory needed - uses global ScyllaDB session pool
    """

    def __init__(self):
        pass

    @Logger.io
    async def create(self, user_entity: UserEntity) -> UserEntity:
        session = await get_scylla_session()

        # Generate UUID7 (time-sortable, distributed-friendly)
        user_id = UUID(str(uuid7()))
        now = datetime.now(timezone.utc)

        query = """
            INSERT INTO "user" (
                id, email, hashed_password, name, role,
                created_at, is_active, is_superuser, is_verified
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

        await asyncio.to_thread(
            session.execute,
            query,
            (
                user_id,
                user_entity.email,
                user_entity.hashed_password,
                user_entity.name,
                user_entity.role.value
                if isinstance(user_entity.role, UserRole)
                else user_entity.role,
                now,
                user_entity.is_active,
                user_entity.is_superuser,
                user_entity.is_verified,
            ),
        )

        # Return created user entity
        return UserEntity(
            id=user_id,
            email=user_entity.email,
            name=user_entity.name,
            role=user_entity.role,
            is_active=user_entity.is_active,
            is_superuser=user_entity.is_superuser,
            is_verified=user_entity.is_verified,
            created_at=now,
        )
