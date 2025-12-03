from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class MqDomainEvent(Protocol):
    @property
    def occurred_at(self) -> datetime:
        """Event occurrence timestamp"""
        ...
