"""
MQ Infrastructure Orchestrator Interface

Handles message queue infrastructure setup for events:
- Kafka topic creation
- Consumer process management
- Seat initialization in Kvrocks
"""

from abc import ABC, abstractmethod
from typing import Dict


class IMqInfraOrchestrator(ABC):
    """
    Orchestrates MQ infrastructure setup for event ticketing system.

    Responsibilities:
    - Kafka topic creation
    - Consumer process management

    Does NOT handle:
    - Kvrocks seat initialization (delegated to IInitEventAndTicketsStateHandler)
    """

    @abstractmethod
    async def setup_mq_infra(
        self,
        *,
        event_id: int,
        seating_config: Dict,
    ) -> None:
        """
        Setup Kafka infrastructure for an event.

        Steps:
        1. Create Kafka topics
        2. Start consumer processes

        Args:
            event_id: Event identifier
            seating_config: Seat configuration (for topic/partition setup)

        Raises:
            InfrastructureSetupError: If setup fails
        """
        pass
