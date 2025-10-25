"""
MQ Infrastructure Orchestrator Interface

Handles message queue infrastructure setup for events:
- Kafka topic creation
- Consumer process management
- Seat initialization in Kvrocks
"""

from abc import ABC, abstractmethod
from typing import Dict
from uuid import UUID


class IMqInfraOrchestrator(ABC):
    """
    Orchestrates MQ infrastructure setup for event ticketing system.

    Responsibilities:
    - Kafka topic creation

    Does NOT handle:
    - Kvrocks seat initialization (delegated to IInitEventAndTicketsStateHandler)
    """

    @abstractmethod
    async def setup_kafka_topics_and_partitions(
        self,
        *,
        event_id: UUID,
        seating_config: Dict,
    ) -> None:
        """
        Setup Kafka topics and partitions for an event.

        Only handles Kafka infrastructure (topics/partitions).
        Does NOT auto-start consumers - they should be started manually via Docker.

        Args:
            event_id: Event identifier
            seating_config: Seat configuration (for partition calculation)

        Raises:
            InfrastructureSetupError: If Kafka setup fails
        """
        pass
