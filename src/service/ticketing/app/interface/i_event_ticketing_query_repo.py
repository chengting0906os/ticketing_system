"""
Event Ticketing Query Repository Interface

統一的活動票務查詢倉儲接口 - CQRS Read Side
取代原本分離的 event_query_repo 和 ticket_query_repo

【設計原則】
- 提供豐富的查詢接口
- 支持多種查詢視角
- 性能優化的查詢方法
- 只負責讀取操作
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import (
    EventTicketingAggregate,
    Ticket,
)


class IEventTicketingQueryRepo(ABC):
    """Event Ticketing 查詢倉儲接口 - CQRS Read Side"""

    @abstractmethod
    async def get_event_aggregate_by_id_with_tickets(
        self, *, event_id: int
    ) -> Optional[EventTicketingAggregate]:
        """
        根據 ID 獲取完整的 Event Aggregate

        Args:
            event_id: 活動 ID

        Returns:
            活動聚合根 (包含所有 tickets) 或 None
        """
        pass

    @abstractmethod
    async def list_events_by_seller(self, *, seller_id: int) -> List[EventTicketingAggregate]:
        """
        獲取賣家的所有活動 (不包含 tickets，性能優化)

        Args:
            seller_id: 賣家 ID

        Returns:
            活動聚合根列表 (tickets 為空列表)
        """
        pass

    @abstractmethod
    async def list_available_events(self) -> List[EventTicketingAggregate]:
        """
        獲取所有可用活動 (不包含 tickets，性能優化)

        Returns:
            可用活動聚合根列表 (tickets 為空列表)
        """
        pass

    @abstractmethod
    async def get_tickets_by_event_and_section(
        self, *, event_id: int, section: str, subsection: int
    ) -> List[Ticket]:
        """
        獲取特定區域的票務

        Args:
            event_id: 活動 ID
            section: 區域
            subsection: 子區域

        Returns:
            票務列表
        """
        pass

    @abstractmethod
    async def get_available_tickets_by_event(self, *, event_id: int) -> List[Ticket]:
        """
        獲取活動的所有可用票務

        Args:
            event_id: 活動 ID

        Returns:
            可用票務列表
        """
        pass

    @abstractmethod
    async def get_reserved_tickets_by_event(self, *, event_id: int) -> List[Ticket]:
        """
        獲取活動的所有已預訂票務

        Args:
            event_id: 活動 ID

        Returns:
            已預訂票務列表
        """
        pass

    @abstractmethod
    async def get_all_tickets_by_event(self, *, event_id: int) -> List[Ticket]:
        """
        獲取活動的所有票務（不限狀態）

        Args:
            event_id: 活動 ID

        Returns:
            所有票務列表
        """
        pass

    @abstractmethod
    async def get_tickets_by_buyer(self, *, buyer_id: int) -> List[Ticket]:
        """
        獲取購買者的所有票務

        Args:
            buyer_id: 購買者 ID

        Returns:
            票務列表
        """
        pass

    @abstractmethod
    async def get_tickets_by_ids(self, *, ticket_ids: List[int]) -> List[Ticket]:
        """
        根據 ID 列表獲取票務

        Args:
            ticket_ids: 票務 ID 列表

        Returns:
            票務列表
        """
        pass

    @abstractmethod
    async def check_tickets_exist_for_event(self, *, event_id: int) -> bool:
        """
        檢查活動是否已有票務

        Args:
            event_id: 活動 ID

        Returns:
            是否存在票務
        """
        pass
