from abc import ABC, abstractmethod

from src.event_ticketing.domain.event_entity import Event


class EventCommandRepo(ABC):
    """事件命令倉庫抽象介面 (Domain Layer) - 處理寫入操作"""

    @abstractmethod
    async def create(self, *, event: Event) -> Event:
        pass

    @abstractmethod
    async def update(self, *, event: Event) -> Event:
        pass

    @abstractmethod
    async def delete(self, *, event_id: int) -> bool:
        pass

    @abstractmethod
    async def release_event_atomically(self, *, event_id: int) -> Event:
        pass
