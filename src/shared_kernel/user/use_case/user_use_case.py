"""
User Management Use Cases (Use Case Layer)
"""

from src.shared_kernel.user.domain.user_entity import UserEntity, UserRole
from src.shared_kernel.user.domain.user_repo import UserRepo
from src.shared_kernel.user.infra.bcrypt_password_hasher import BcryptPasswordHasher


async def create_user(
    user_repo: UserRepo,
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
    return await user_repo.create(user_entity)


async def get_user_by_id(user_repo: UserRepo, user_id: int) -> UserEntity | None:
    return await user_repo.get_by_id(user_id)
