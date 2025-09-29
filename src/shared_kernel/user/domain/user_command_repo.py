from abc import ABC, abstractmethod

from src.shared_kernel.user.domain.user_entity import UserEntity


class UserCommandRepo(ABC):
    """用戶命令倉庫抽象介面 (Domain Layer) - 處理寫入操作"""

    @abstractmethod
    async def create(self, user_entity: UserEntity) -> UserEntity:
        pass
