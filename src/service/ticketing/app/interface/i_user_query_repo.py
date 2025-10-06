from abc import ABC, abstractmethod
from typing import Optional

from src.service.ticketing.domain.entity.user_entity import UserEntity


class IUserQueryRepo(ABC):
    """用戶查詢倉庫抽象介面 (Domain Layer) - 處理讀取操作"""

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[UserEntity]:
        pass

    @abstractmethod
    async def get_by_id(self, user_id: int) -> Optional[UserEntity]:
        pass

    @abstractmethod
    async def exists_by_email(self, email: str) -> bool:
        pass

    @abstractmethod
    async def verify_password(self, email: str, plain_password: str) -> Optional[UserEntity]:
        pass
