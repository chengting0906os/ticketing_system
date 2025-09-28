from abc import ABC, abstractmethod
from typing import List, Optional

from .mq_domain_event import MqDomainEvent


class MqPublisher(ABC):
    @abstractmethod
    async def publish(
        self, *, event: MqDomainEvent, topic: str, partition_key: Optional[str] = None
    ) -> bool:
        pass

    @abstractmethod
    async def publish_batch(
        self, *, events: List[MqDomainEvent], topic: str, partition_key: Optional[str] = None
    ) -> bool:
        pass
