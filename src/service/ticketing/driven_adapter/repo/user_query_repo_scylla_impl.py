import asyncio
from typing import Optional
from uuid import UUID

from pydantic import SecretStr
from cassandra.query import SimpleStatement, ConsistencyLevel

from src.platform.database.scylla_setting import get_scylla_session
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.domain.entity.user_entity import UserEntity, UserRole
from src.service.ticketing.app.interface.i_user_query_repo import IUserQueryRepo
from src.service.ticketing.driven_adapter.security.bcrypt_password_hasher import (
    BcryptPasswordHasher,
)


class UserQueryRepoScyllaImpl(IUserQueryRepo):
    """
    ScyllaDB User Query Repository

    Uses secondary index on email for login queries
    """

    def __init__(self):
        self.password_hasher = BcryptPasswordHasher()

    @Logger.io
    async def get_by_email(self, email: str) -> Optional[UserEntity]:
        session = await get_scylla_session()

        # Uses secondary index (users_email_idx)
        query = SimpleStatement(
            """
            SELECT id, email, hashed_password, name, role,
                   created_at, is_active, is_superuser, is_verified
            FROM "user"
            WHERE email = %s
            """,
            consistency_level=ConsistencyLevel.LOCAL_ONE,
        )

        future = session.execute_async(query, (email,))
        result = await asyncio.to_thread(future.result)
        row = result.one()

        if not row:
            return None

        return self._row_to_entity(row)

    @Logger.io
    async def get_by_id(self, user_id: UUID) -> Optional[UserEntity]:
        session = await get_scylla_session()

        query = SimpleStatement(
            """
            SELECT id, email, hashed_password, name, role,
                   created_at, is_active, is_superuser, is_verified
            FROM "user"
            WHERE id = %s
            """,
            consistency_level=ConsistencyLevel.LOCAL_ONE,
        )

        future = session.execute_async(query, (user_id,))
        result = await asyncio.to_thread(future.result)
        row = result.one()

        if not row:
            return None

        return self._row_to_entity(row)

    @Logger.io
    async def exists_by_email(self, email: str) -> bool:
        session = await get_scylla_session()

        query = SimpleStatement(
            """
            SELECT id
            FROM "user"
            WHERE email = %s
            """,
            consistency_level=ConsistencyLevel.LOCAL_ONE,
        )

        future = session.execute_async(query, (email,))
        result = await asyncio.to_thread(future.result)

        return result.one() is not None

    @Logger.io
    async def verify_password(self, email: str, plain_password: str) -> Optional[UserEntity]:
        session = await get_scylla_session()

        query = SimpleStatement(
            """
            SELECT id, email, hashed_password, name, role,
                   created_at, is_active, is_superuser, is_verified
            FROM "user"
            WHERE email = %s
            """,
            consistency_level=ConsistencyLevel.LOCAL_ONE,
        )

        future = session.execute_async(query, (email,))
        result = await asyncio.to_thread(future.result)
        row = result.one()

        if not row:
            return None

        # Verify password using bcrypt
        secret_password = SecretStr(plain_password)

        if not self.password_hasher.verify_password(
            plain_password=secret_password, hashed_password=row.hashed_password
        ):
            return None

        return self._row_to_entity(row)

    def _row_to_entity(self, row) -> UserEntity:
        return UserEntity(
            id=row.id,
            email=row.email,
            name=row.name,
            role=UserRole(row.role),
            is_active=row.is_active,
            is_superuser=row.is_superuser,
            is_verified=row.is_verified,
            created_at=row.created_at,
        )
