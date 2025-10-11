"""
MQ Infrastructure Orchestrator Implementation

Handles Kafka topics and partitions setup for events.
"""

from typing import Dict

from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_mq_infra_orchestrator import IMqInfraOrchestrator
from src.service.ticketing.shared_kernel.app.interface.i_kafka_config_service import (
    IKafkaConfigService,
)


class MqInfraOrchestrator(IMqInfraOrchestrator):
    """
    Orchestrates Kafka infrastructure setup for event ticketing system.

    Responsibilities:
    - Kafka topics and partitions creation for new events

    Does NOT handle:
    - Consumer management (consumers run in Docker containers)
    - Kvrocks seat initialization (delegated to IInitEventAndTicketsStateHandler)
    """

    def __init__(
        self,
        kafka_service: IKafkaConfigService,
    ):
        self.kafka_service = kafka_service

    @Logger.io
    async def setup_kafka_topics_and_partitions(
        self,
        *,
        event_id: int,
        seating_config: Dict,
    ) -> None:
        """
        Setup Kafka topics and partitions for a new event.

        Only handles Kafka infrastructure (topics/partitions).
        Consumers are managed separately via Docker.
        """
        try:
            Logger.base.info(f'🚀 Setting up Kafka topics and partitions for event {event_id}')

            # Setup Kafka topics and partitions based on seating config
            infrastructure_success = await self.kafka_service.setup_event_infrastructure(
                event_id=event_id, seating_config=seating_config
            )

            if not infrastructure_success:
                Logger.base.warning(f'⚠️ Kafka setup failed for event {event_id}, continuing...')

            Logger.base.info(f'✅ Kafka topics and partitions setup completed for event {event_id}')

        except Exception as e:
            Logger.base.error(f'❌ Kafka topics and partitions setup failed: {e}')
            raise
