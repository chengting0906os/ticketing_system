from abc import ABC, abstractmethod

from src.service.ticketing.domain.entity.user_entity import UserEntity


class IUserCommandRepo(ABC):
    """User Command Repository Abstract Interface (Domain Layer) - Handles write operations"""

    @abstractmethod
    async def create(self, user_entity: UserEntity) -> UserEntity:
        pass
