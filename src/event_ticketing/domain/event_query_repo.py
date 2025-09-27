from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional

from src.event_ticketing.domain.event_entity import Event

if TYPE_CHECKING:
    from src.shared_kernel.user.infra.user_model import UserModel


class EventQueryRepo(ABC):
    """事件查詢倉庫抽象介面 (Domain Layer) - 處理讀取操作"""

    @abstractmethod
    async def get_by_id(self, *, event_id: int) -> Optional[Event]:
        pass

    @abstractmethod
    async def get_by_id_with_seller(
        self, *, event_id: int
    ) -> tuple[Optional[Event], Optional['UserModel']]:
        pass

    @abstractmethod
    async def get_by_seller(self, *, seller_id: int) -> List[Event]:
        pass

    @abstractmethod
    async def list_available(self) -> List[Event]:
        pass
