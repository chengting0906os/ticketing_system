from datetime import datetime
from enum import Enum
from typing import Optional

import attrs
from pydantic import SecretStr

from src.platform.exception.exceptions import (
    AuthenticationError,
    DomainError,
    ForbiddenError,
    LoginError,
)


class UserRole(str, Enum):
    SELLER = 'seller'
    BUYER = 'buyer'
    ADMIN = 'admin'


@attrs.define
class UserEntity:
    email: str = ''
    name: str = ''
    hashed_password: str = attrs.field(default='', repr=False)  # Hide from repr for security
    id: Optional[int] = None
    role: UserRole = UserRole.BUYER
    is_active: bool = True
    is_superuser: bool = False
    is_verified: bool = False
    created_at: Optional[datetime] = None

    def validate_for_authentication(self) -> None:
        if not self.email:
            raise AuthenticationError('LOGIN_BAD_CREDENTIALS')

        if not self.is_active:
            raise ForbiddenError('User is inactive')

    def validate_exists(self) -> None:
        if not self.id or not self.email:
            raise AuthenticationError('User not found')

    def validate_active(self) -> None:
        from src.platform.exception.exceptions import ForbiddenError

        if not self.is_active:
            raise ForbiddenError('User is inactive')

    @staticmethod
    def validate_user_exists(user_entity: Optional['UserEntity']) -> 'UserEntity':
        if not user_entity:
            raise LoginError('LOGIN_BAD_CREDENTIALS')

        return user_entity

    @staticmethod
    def validate_role(role: UserRole) -> None:
        """Validate if the role is valid"""
        valid_roles = [r.value for r in UserRole.__members__.values()]
        if role not in valid_roles:
            raise DomainError(f'Invalid role: {role}. Must be one of: {", ".join(valid_roles)}')

    def set_password(self, plain_password: str, password_hasher) -> None:
        """Set password using provided password hasher"""
        from src.service.ticketing.app.interface.i_password_hasher import IPasswordHasher

        if not isinstance(password_hasher, IPasswordHasher):
            raise TypeError('password_hasher must implement PasswordHasher interface')

        # Use SecretStr to protect sensitive password data
        secret_password = SecretStr(plain_password)
        self.hashed_password = password_hasher.hash_password(plain_password=secret_password)
