from datetime import datetime
from typing import Dict, Any, Optional


class SeatInitializationEvent:
    """
    座位初始化事件
    用於向 RocksDB 發送座位初始化指令
    """

    def __init__(
        self,
        *,
        event_id: int,
        seat_id: str,
        section: str,
        subsection: int,
        row: int,
        seat: int,
        price: int,
        occurred_at: Optional[datetime] = None,
    ):
        self.event_id = event_id
        self.seat_id = seat_id
        self.section = section
        self.subsection = subsection
        self.row = row
        self.seat = seat
        self.price = price
        self.occurred_at = occurred_at or datetime.now()

    @property
    def aggregate_id(self) -> int:
        """業務聚合根ID，用於分區和關聯"""
        return self.event_id

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式，用於 Kafka 消息"""
        return {
            'event_type': 'SeatInitialization',
            'aggregate_id': self.aggregate_id,
            'data': {
                'action': 'INITIALIZE',
                'seat_id': self.seat_id,
                'event_id': self.event_id,
                'price': self.price,
                'section': self.section,
                'subsection': self.subsection,
                'row': self.row,
                'seat': self.seat,
            },
            'occurred_at': self.occurred_at.isoformat(),
        }
