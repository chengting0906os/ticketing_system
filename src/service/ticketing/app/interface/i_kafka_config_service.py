from abc import ABC, abstractmethod
from typing import Dict


class IKafkaConfigService(ABC):
    """Kafka configuration service interface"""

    @abstractmethod
    async def setup_event_infrastructure(self, *, event_id: int, seating_config: Dict) -> bool:
        """Setup Kafka topics and partition strategy for new event"""
        ...
