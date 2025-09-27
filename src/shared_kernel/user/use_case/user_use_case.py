"""
User Management Use Cases (Use Case Layer)
"""

from fastapi import HTTPException, status

from src.shared_kernel.user.domain.user_entity import UserEntity, UserRole
from src.shared_kernel.user.domain.user_repo import UserRepo


async def create_user(
    user_repo: UserRepo,
    email: str,
    password: str,
    name: str,
    role: UserRole = UserRole.BUYER,
) -> UserEntity:
    if await user_repo.exists_by_email(email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='User already exists')

    user_entity = UserEntity(
        email=email, name=name, role=role, is_active=True, is_superuser=False, is_verified=False
    )

    return await user_repo.create_with_password(user_entity, password)


async def get_user_by_id(user_repo: UserRepo, user_id: int) -> UserEntity:
    user_entity = await user_repo.get_by_id(user_id)
    validated_user = UserEntity.validate_user_exists(user_entity)
    validated_user.validate_active()

    return validated_user
