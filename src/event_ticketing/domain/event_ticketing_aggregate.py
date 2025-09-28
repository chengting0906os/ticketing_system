"""
Event Ticketing Aggregate - 活動票務聚合根

【DDD 設計原則】
- EventTicketingAggregate 是聚合根 (Aggregate Root)
- Event 和 Ticket 都是聚合內的實體
- 所有票務操作都通過聚合根進行
- 保證事務一致性和業務規則

【業務不變式】
- 活動必須有有效的座位配置
- 票務數量必須與座位配置一致
- 票務狀態變更必須符合業務規則
- 活動狀態和票務狀態必須保持一致
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

import attrs

from src.shared.logging.loguru_io import Logger
from src.shared_kernel.domain.enum.ticket_status import TicketStatus
from src.shared_kernel.domain.event_status import EventStatus


@attrs.define
class Ticket:
    """
    Ticket Entity - 聚合內實體

    票務實體現在是 EventTicketingAggregate 的一部分
    不再是獨立的聚合根
    """

    event_id: int
    section: str
    subsection: int
    row: int
    seat: int
    price: int
    status: TicketStatus
    buyer_id: Optional[int] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    reserved_at: Optional[datetime] = None

    @property
    def seat_identifier(self) -> str:
        """座位標識符"""
        return f'{self.section}-{self.subsection}-{self.row}-{self.seat}'

    @Logger.io
    def reserve(self, *, buyer_id: int) -> None:
        """預訂票務"""
        if self.status != TicketStatus.AVAILABLE:
            raise ValueError(f'Cannot reserve ticket with status {self.status}')

        self.status = TicketStatus.RESERVED
        self.buyer_id = buyer_id
        self.reserved_at = datetime.now(timezone.utc)

    @Logger.io
    def sell(self) -> None:
        """售出票務"""
        if self.status != TicketStatus.RESERVED:
            raise ValueError(f'Cannot sell ticket with status {self.status}')

        self.status = TicketStatus.SOLD

    @Logger.io
    def release(self) -> None:
        """釋放票務"""
        if self.status != TicketStatus.RESERVED:
            raise ValueError(f'Cannot release ticket with status {self.status}')

        self.status = TicketStatus.AVAILABLE
        self.buyer_id = None
        self.reserved_at = None

    @Logger.io
    def cancel_reservation(self, *, buyer_id: int) -> None:
        """取消預訂"""
        if self.status != TicketStatus.RESERVED:
            raise ValueError(f'Cannot cancel reservation for ticket with status {self.status}')

        if self.buyer_id != buyer_id:
            raise ValueError('Cannot cancel reservation that belongs to another buyer')

        self.release()


@attrs.define
class Event:
    """
    Event Entity - 聚合內實體

    活動實體現在是 EventTicketingAggregate 的一部分
    """

    name: str
    description: str
    seller_id: int
    venue_name: str
    seating_config: Dict
    is_active: bool = True
    status: EventStatus = EventStatus.AVAILABLE
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@attrs.define
class EventTicketingAggregate:
    """
    Event Ticketing Aggregate Root - 活動票務聚合根

    這是整個活動票務系統的聚合根，包含：
    1. Event 實體 - 活動資訊
    2. Tickets 集合 - 所有票務

    負責：
    1. 活動的生命週期管理
    2. 票務的創建和管理
    3. 業務規則的執行
    4. 聚合內一致性保證
    """

    # Event 實體
    event: Event

    # Tickets 集合 - 聚合內實體
    tickets: List[Ticket] = attrs.field(factory=list)

    @classmethod
    @Logger.io
    def create_event_with_tickets(
        cls,
        *,
        name: str,
        description: str,
        seller_id: int,
        venue_name: str,
        seating_config: Dict,
        is_active: bool = True,
    ) -> 'EventTicketingAggregate':
        """
        創建帶票務的活動 - 聚合根工廠方法

        這是創建 EventTicketingAggregate 的唯一正確方式
        確保活動和票務同時創建，保持聚合一致性
        """

        # 驗證座位配置
        cls._validate_seating_config(seating_config)

        # 創建 Event 實體
        event = Event(
            name=name,
            description=description,
            seller_id=seller_id,
            venue_name=venue_name,
            seating_config=seating_config,
            is_active=is_active,
            status=EventStatus.AVAILABLE,
            created_at=datetime.now(timezone.utc),
        )

        # 創建聚合根
        aggregate = cls(event=event, tickets=[])

        return aggregate

    @Logger.io
    def generate_tickets(self) -> None:
        """
        根據座位配置生成票務

        必須在活動持久化後調用（需要 event.id）
        """
        if not self.event.id:
            raise ValueError('Event must be persisted before generating tickets')

        if self.tickets:
            raise ValueError('Tickets already generated for this event')

        self.tickets = self._generate_tickets_from_seating_config()
        Logger.base.info(f'Generated {len(self.tickets)} tickets for event {self.event.id}')

    def _generate_tickets_from_seating_config(self) -> List[Ticket]:
        """根據座位配置生成票務實體"""
        if not self.event.id:
            raise ValueError('Event must have an ID before generating tickets')

        tickets = []
        sections = self.event.seating_config.get('sections', [])

        for section in sections:
            section_name = section['name']
            section_price = int(section['price'])
            subsections = section['subsections']

            for subsection in subsections:
                subsection_number = subsection['number']
                rows = subsection['rows']
                seats_per_row = subsection['seats_per_row']

                for row in range(1, rows + 1):
                    for seat in range(1, seats_per_row + 1):
                        ticket = Ticket(
                            event_id=self.event.id,
                            section=section_name,
                            subsection=subsection_number,
                            row=row,
                            seat=seat,
                            price=section_price,
                            status=TicketStatus.AVAILABLE,
                        )
                        tickets.append(ticket)

        return tickets

    @staticmethod
    def _validate_seating_config(seating_config: Dict) -> None:
        """驗證座位配置的業務規則"""
        if not isinstance(seating_config, dict) or 'sections' not in seating_config:
            raise ValueError('Invalid seating configuration: must contain sections')

        sections = seating_config.get('sections', [])
        if not isinstance(sections, list) or len(sections) == 0:
            raise ValueError('Invalid seating configuration: sections must be a non-empty list')

        for section in sections:
            if not isinstance(section, dict):
                raise ValueError('Invalid seating configuration: each section must be a dictionary')

            # Check required fields
            required_fields = ['name', 'price', 'subsections']
            for field in required_fields:
                if field not in section:
                    raise ValueError(
                        f'Invalid seating configuration: section missing required field "{field}"'
                    )

            # Validate price
            price = section.get('price')
            if not isinstance(price, (int, float)) or price < 0:
                raise ValueError('Ticket price must over 0')

            # Validate subsections
            subsections = section.get('subsections', [])
            if not isinstance(subsections, list) or len(subsections) == 0:
                raise ValueError(
                    'Invalid seating configuration: each section must have subsections'
                )

            for subsection in subsections:
                if not isinstance(subsection, dict):
                    raise ValueError(
                        'Invalid seating configuration: each subsection must be a dictionary'
                    )

                required_subsection_fields = ['number', 'rows', 'seats_per_row']
                for field in required_subsection_fields:
                    if field not in subsection:
                        raise ValueError(
                            f'Invalid seating configuration: subsection missing required field "{field}"'
                        )

                # Validate numeric fields
                for field in ['number', 'rows', 'seats_per_row']:
                    value = subsection.get(field)
                    if not isinstance(value, int) or value <= 0:
                        raise ValueError(
                            f'Invalid seating configuration: {field} must be a positive integer'
                        )

    @Logger.io
    def reserve_tickets(self, *, ticket_ids: List[int], buyer_id: int) -> List[Ticket]:
        """
        預訂票務 - 聚合內業務邏輯

        Args:
            ticket_ids: 要預訂的票務 ID 列表
            buyer_id: 購買者 ID

        Returns:
            已預訂的票務列表
        """
        reserved_tickets = []

        for ticket_id in ticket_ids:
            ticket = self._find_ticket_by_id(ticket_id)
            if not ticket:
                raise ValueError(f'Ticket {ticket_id} not found in this event')

            # 檢查票務狀態
            if ticket.status != TicketStatus.AVAILABLE:
                raise ValueError(f'Ticket {ticket_id} is not available for reservation')

            # 執行預訂
            ticket.reserve(buyer_id=buyer_id)
            reserved_tickets.append(ticket)

        # 更新活動狀態
        self.update_event_status_based_on_tickets()

        return reserved_tickets

    @Logger.io
    def cancel_ticket_reservations(self, *, ticket_ids: List[int], buyer_id: int) -> List[Ticket]:
        """
        取消票務預訂 - 聚合內業務邏輯
        """
        cancelled_tickets = []

        for ticket_id in ticket_ids:
            ticket = self._find_ticket_by_id(ticket_id)
            if not ticket:
                raise ValueError(f'Ticket {ticket_id} not found in this event')

            # 檢查票務狀態和所有權
            if ticket.buyer_id != buyer_id:
                raise ValueError(f'Ticket {ticket_id} does not belong to buyer {buyer_id}')

            # 執行取消
            ticket.cancel_reservation(buyer_id=buyer_id)
            cancelled_tickets.append(ticket)

        # 更新活動狀態
        self.update_event_status_based_on_tickets()

        return cancelled_tickets

    @Logger.io
    def finalize_tickets_as_sold(self, *, ticket_ids: List[int]) -> List[Ticket]:
        """
        將票務標記為已售出
        """
        sold_tickets = []

        for ticket_id in ticket_ids:
            ticket = self._find_ticket_by_id(ticket_id)
            if not ticket:
                raise ValueError(f'Ticket {ticket_id} not found in this event')

            # 執行售出
            ticket.sell()
            sold_tickets.append(ticket)

        # 更新活動狀態
        self.update_event_status_based_on_tickets()

        return sold_tickets

    def _find_ticket_by_id(self, ticket_id: int) -> Optional[Ticket]:
        """在聚合內查找票務"""
        for ticket in self.tickets:
            if ticket.id == ticket_id:
                return ticket
        return None

    def get_tickets_by_section(self, *, section: str, subsection: int) -> List[Ticket]:
        """獲取特定區域的票務"""
        return [
            ticket
            for ticket in self.tickets
            if ticket.section == section and ticket.subsection == subsection
        ]

    def get_available_tickets(self) -> List[Ticket]:
        """獲取所有可用票務"""
        return [t for t in self.tickets if t.status == TicketStatus.AVAILABLE]

    def get_reserved_tickets(self) -> List[Ticket]:
        """獲取所有已預訂票務"""
        return [t for t in self.tickets if t.status == TicketStatus.RESERVED]

    def get_sold_tickets(self) -> List[Ticket]:
        """獲取所有已售出票務"""
        return [t for t in self.tickets if t.status == TicketStatus.SOLD]

    @property
    def total_tickets_count(self) -> int:
        """總票數"""
        return len(self.tickets)

    @property
    def available_tickets_count(self) -> int:
        """可用票數"""
        return len(self.get_available_tickets())

    @property
    def reserved_tickets_count(self) -> int:
        """已預訂票數"""
        return len(self.get_reserved_tickets())

    @property
    def sold_tickets_count(self) -> int:
        """已售出票數"""
        return len(self.get_sold_tickets())

    @Logger.io
    def update_event_status_based_on_tickets(self) -> None:
        """根據票務狀態更新活動狀態"""
        if self.available_tickets_count == 0 and self.total_tickets_count > 0:
            self.event.status = EventStatus.SOLD_OUT
        elif self.total_tickets_count > 0:
            self.event.status = EventStatus.AVAILABLE
        else:
            self.event.status = EventStatus.DRAFT

    def get_statistics(self) -> dict:
        """獲取聚合統計信息"""
        return {
            'event_id': self.event.id,
            'event_name': self.event.name,
            'event_status': self.event.status.value,
            'total_tickets': self.total_tickets_count,
            'available_tickets': self.available_tickets_count,
            'reserved_tickets': self.reserved_tickets_count,
            'sold_tickets': self.sold_tickets_count,
            'total_revenue': sum(t.price for t in self.get_sold_tickets()),
            'potential_revenue': sum(t.price for t in self.tickets),
        }
