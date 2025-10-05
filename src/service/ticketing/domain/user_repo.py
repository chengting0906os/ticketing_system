from abc import ABC, abstractmethod
from typing import Optional

from src.service.ticketing.domain.user_entity import UserEntity


class UserRepo(ABC):
    """用戶倉庫抽象介面 (Domain Layer)"""

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[UserEntity]:
        pass

    @abstractmethod
    async def get_by_id(self, user_id: int) -> Optional[UserEntity]:
        pass

    @abstractmethod
    async def create(self, user_entity: UserEntity) -> UserEntity:
        pass

    @abstractmethod
    async def exists_by_email(self, email: str) -> bool:
        pass

    @abstractmethod
    async def verify_password(self, email: str, plain_password: str) -> Optional[UserEntity]:
        pass
