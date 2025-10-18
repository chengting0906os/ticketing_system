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

from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import (
    EventTicketingAggregate,
    Ticket,
)
from src.service.ticketing.domain.enum.ticket_status import TicketStatus


class IEventTicketingCommandRepo(ABC):
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
    async def create_event_aggregate_with_batch_tickets(
        self,
        *,
        event_aggregate: EventTicketingAggregate,
        ticket_tuples: Optional[List[tuple]] = None,
    ) -> EventTicketingAggregate:
        """
        使用高效能批量方式創建帶有大量票務的 Event Aggregate

        注意：這個方法假設 Event 已經存在並且有 ID
        專門用於需要創建大量票務的場景（如數萬張票）

        Args:
            event_aggregate: 已有 Event ID 的活動聚合根
            ticket_tuples: 預先準備好的批量插入資料格式（可選）

        Returns:
            保存後的聚合根（包含所有票務 ID）
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
    async def get_ticket_ids_by_seat_identifiers(
        self, *, event_id: int, seat_identifiers: List[str]
    ) -> List[int]:
        """
        根據座位標識符獲取票券 ID

        此方法用於支援寫入操作（如創建 booking），屬於 command repo 的查詢輔助方法

        Args:
            event_id: 活動 ID
            seat_identifiers: 座位標識符列表 (例如: ['A-1-1-1', 'A-1-1-2'])

        Returns:
            票券 ID 列表
        """
        pass

    @abstractmethod
    async def get_tickets_by_ids(self, *, ticket_ids: List[int]) -> List[Ticket]:
        """
        根據票券 ID 獲取票券詳細資訊

        此方法用於支援寫入操作（如計算訂單總價），屬於 command repo 的查詢輔助方法

        Args:
            ticket_ids: 票券 ID 列表

        Returns:
            票券列表
        """
        pass
