from datetime import datetime
from typing import Protocol, Union, runtime_checkable

from pydantic import UUID7 as UUID


@runtime_checkable
class MqDomainEvent(Protocol):
    """
    領域事件協議定義

    【MVP原則】所有領域事件必須包含的最基本屬性：
    - aggregate_id: 業務實體ID（如booking_id）
    - occurred_at: 事件發生時間
    """

    @property
    def aggregate_id(self) -> Union[int, str, UUID]:
        """業務聚合根ID，用於分區和關聯 (支援 int, str, UUID)"""
        ...

    @property
    def occurred_at(self) -> datetime:
        """事件發生時間戳"""
        ...
