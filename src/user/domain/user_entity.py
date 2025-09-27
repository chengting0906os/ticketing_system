from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from src.shared.exception.exceptions import AuthenticationError, ForbiddenError


class UserRole(str, Enum):
    SELLER = 'seller'
    BUYER = 'buyer'
    ADMIN = 'admin'


@dataclass
class UserEntity:
    """用戶業務實體 (Domain Layer)"""

    id: Optional[int] = None
    email: str = ''
    name: str = ''
    role: UserRole = UserRole.BUYER
    is_active: bool = True
    is_superuser: bool = False
    is_verified: bool = False
    created_at: Optional[datetime] = None

    def validate_for_authentication(self) -> None:
        if not self:
            raise AuthenticationError('Invalid credentials')

        if not self.is_active:
            raise ForbiddenError('User is inactive')

    def validate_exists(self) -> None:
        if not self:
            raise AuthenticationError('User not found')

    def validate_active(self) -> None:
        from src.shared.exception.exceptions import ForbiddenError

        if not self.is_active:
            raise ForbiddenError('User is inactive')

    @staticmethod
    def validate_user_exists(user_entity: Optional['UserEntity']) -> 'UserEntity':
        if not user_entity:
            raise AuthenticationError('Invalid credentials')

        return user_entity
