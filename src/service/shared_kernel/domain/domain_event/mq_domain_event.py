from datetime import datetime
from typing import Protocol, Union, runtime_checkable

from uuid_utils import UUID


@runtime_checkable
class MqDomainEvent(Protocol):
    """
    Domain Event Protocol Definition

    [MVP Principle] Essential attributes that all domain events must contain:
    - aggregate_id: Business entity ID (e.g., booking_id)
    - occurred_at: Event occurrence time
    """

    @property
    def aggregate_id(self) -> Union[int, str, UUID]:
        """Business aggregate root ID, used for partitioning and association (supports int, str, UUID)"""
        ...

    @property
    def occurred_at(self) -> datetime:
        """Event occurrence timestamp"""
        ...
