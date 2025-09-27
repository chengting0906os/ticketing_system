from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional


if TYPE_CHECKING:
    from src.shared_kernel.user.infra.user_model import UserModel

from src.event_ticketing.domain.event_entity import Event


class EventRepo(ABC):
    @abstractmethod
    async def create(self, *, event: Event) -> Event:
        pass

    @abstractmethod
    async def get_by_id(self, *, event_id: int) -> Optional[Event]:
        pass

    @abstractmethod
    async def get_by_id_with_seller(
        self, *, event_id: int
    ) -> tuple[Optional[Event], Optional['UserModel']]:
        pass

    @abstractmethod
    async def update(self, *, event: Event) -> Event:
        pass

    @abstractmethod
    async def delete(self, *, event_id: int) -> bool:
        pass

    @abstractmethod
    async def get_by_seller(self, *, seller_id: int) -> List[Event]:
        pass

    @abstractmethod
    async def list_available(self) -> List[Event]:
        pass

    @abstractmethod
    async def release_event_atomically(self, *, event_id: int) -> Event:
        pass
