"""
Event Ticketing Command Repository Interface

統一的活動票務命令倉儲接口 - CQRS Write Side
取代原本分離的 event_command_repo 和 ticket_command_repo

【設計原則】
- 以 Event Aggregate 為操作單位
- 保證聚合的事務一致性
- 只負責寫入操作
- 支持批量操作優化
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.event_ticketing.domain.event_ticketing_aggregate import EventTicketingAggregate, Ticket
from src.shared_kernel.domain.enum.ticket_status import TicketStatus


class EventTicketingCommandRepo(ABC):
    """Event Ticketing 命令倉儲接口 - CQRS Write Side"""

    @abstractmethod
    async def create_event_aggregate(
        self, *, event_aggregate: EventTicketingAggregate
    ) -> EventTicketingAggregate:
        """
        創建 Event Aggregate (包含 Event 和 Tickets)

        Args:
            event_aggregate: 活動聚合根

        Returns:
            保存後的聚合根 (包含生成的 ID)
        """
        pass

    @abstractmethod
    async def update_event_aggregate(
        self, *, event_aggregate: EventTicketingAggregate
    ) -> EventTicketingAggregate:
        """
        更新 Event Aggregate

        Args:
            event_aggregate: 要更新的活動聚合根

        Returns:
            更新後的聚合根
        """
        pass

    @abstractmethod
    async def update_tickets_status(
        self, *, ticket_ids: List[int], status: TicketStatus, buyer_id: Optional[int] = None
    ) -> List[Ticket]:
        """
        批量更新票務狀態

        Args:
            ticket_ids: 票務 ID 列表
            status: 新狀態
            buyer_id: 購買者 ID (可選)

        Returns:
            更新後的票務列表
        """
        pass

    @abstractmethod
    async def delete_event_aggregate(self, *, event_id: int) -> bool:
        """
        刪除 Event Aggregate (cascade delete tickets)

        Args:
            event_id: 活動 ID

        Returns:
            是否刪除成功
        """
        pass

    @abstractmethod
    async def reserve_tickets_for_booking(
        self, *, event_id: int, ticket_ids: List[int], buyer_id: int, booking_id: int
    ) -> List[Ticket]:
        """
        為訂單預訂票務

        Args:
            event_id: 活動 ID
            ticket_ids: 票務 ID 列表
            buyer_id: 購買者 ID
            booking_id: 訂單 ID

        Returns:
            預訂的票務列表
        """
        pass

    @abstractmethod
    async def release_tickets_from_booking(
        self, *, event_id: int, ticket_ids: List[int], booking_id: int
    ) -> List[Ticket]:
        """
        從訂單釋放票務

        Args:
            event_id: 活動 ID
            ticket_ids: 票務 ID 列表
            booking_id: 訂單 ID

        Returns:
            釋放的票務列表
        """
        pass

    @abstractmethod
    async def finalize_tickets_as_sold(
        self, *, event_id: int, ticket_ids: List[int], booking_id: int
    ) -> List[Ticket]:
        """
        將票務標記為已售出

        Args:
            event_id: 活動 ID
            ticket_ids: 票務 ID 列表
            booking_id: 訂單 ID

        Returns:
            已售出的票務列表
        """
        pass
