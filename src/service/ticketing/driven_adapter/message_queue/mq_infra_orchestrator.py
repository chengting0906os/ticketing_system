"""
MQ Infrastructure Orchestrator Implementation

Handles MQ infrastructure setup for events outside of the main transaction.
"""

import asyncio
import os
from typing import Dict

from src.platform.config.core_setting import settings
from src.platform.constant.path import BASE_DIR
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.kafka_constant_builder import KafkaConsumerGroupBuilder
from src.service.ticketing.app.interface.i_mq_infra_orchestrator import IMqInfraOrchestrator
from src.service.ticketing.shared_kernel.app.interface.i_kafka_config_service import (
    IKafkaConfigService,
)


class MqInfraOrchestrator(IMqInfraOrchestrator):
    """
    Orchestrates MQ infrastructure setup for event ticketing system.

    Responsibilities:
    - Kafka topic creation
    - Consumer process management

    Does NOT handle:
    - Kvrocks seat initialization (use case delegates separately to IInitEventAndTicketsStateHandler)
    """

    def __init__(
        self,
        kafka_service: IKafkaConfigService,
    ):
        self.kafka_service = kafka_service

    @Logger.io
    async def setup_mq_infra(
        self,
        *,
        event_id: int,
        seating_config: Dict,
    ) -> None:
        """
        Setup Kafka infrastructure for an event.

        Steps:
        1. Start consumer processes
        2. Setup Kafka infrastructure (topics, partitions)
        """
        try:
            Logger.base.info(f'🚀 Setting up MQ infrastructure for event {event_id}')

            # 1. Start consumers first (they need to be ready before messages arrive)
            await self._start_consumers(event_id=event_id)

            # 2. Setup Kafka topics and partitions
            infrastructure_success = await self.kafka_service.setup_event_infrastructure(
                event_id=event_id, seating_config=seating_config
            )

            if not infrastructure_success:
                Logger.base.warning(f'⚠️ Kafka setup failed for event {event_id}, continuing...')

            Logger.base.info(f'✅ MQ infrastructure setup completed for event {event_id}')

        except Exception as e:
            Logger.base.error(f'❌ MQ infrastructure setup failed: {e}')
            raise

    @Logger.io
    async def _start_consumers(self, *, event_id: int) -> None:
        """
        Start consumer processes for event (1-2-1 architecture).

        Architecture:
        - ticketing: 1 consumer (PostgreSQL state)
        - seat_reservation: 2 consumers (Kvrocks state, seat selection)
        """
        try:
            project_root = BASE_DIR

            consumers = [
                {
                    'name': 'ticketing_mq_consumer',
                    'module': settings.TICKETING_CONSUMER_MODULE,
                    'group_id': KafkaConsumerGroupBuilder.ticketing_service(event_id=event_id),
                    'instance_id': 1,
                },
                {
                    'name': 'seat_reservation_mq_consumer',
                    'module': settings.SEAT_RESERVATION_CONSUMER_MODULE,
                    'group_id': KafkaConsumerGroupBuilder.seat_reservation_service(
                        event_id=event_id
                    ),
                    'instance_id': 1,
                },
            ]

            processes = []
            for consumer_config in consumers:
                try:
                    env = os.environ.copy()
                    env['EVENT_ID'] = str(event_id)
                    env['PYTHONPATH'] = str(project_root)
                    env['CONSUMER_GROUP_ID'] = str(consumer_config['group_id'])
                    env['CONSUMER_INSTANCE_ID'] = str(consumer_config['instance_id'])

                    cmd = ['uv', 'run', 'python', '-m', str(consumer_config['module'])]

                    process = await asyncio.create_subprocess_exec(
                        *cmd,
                        cwd=project_root,
                        env=env,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        start_new_session=True,
                    )

                    processes.append((consumer_config['name'], process))
                    Logger.base.info(
                        f'✅ Started {consumer_config["name"]} '
                        f'(PID: {process.pid}, Group: {consumer_config["group_id"]})'
                    )

                except Exception as e:
                    Logger.base.error(f'❌ Failed to start {consumer_config["name"]}: {e}')

            # Brief wait for consumers to start
            await asyncio.sleep(1)

            Logger.base.info(f'📊 [1-2-1 CONFIG] Total consumers started: {len(processes)}')

        except Exception as e:
            Logger.base.error(f'❌ Auto-start consumers failed: {e}')
            raise
