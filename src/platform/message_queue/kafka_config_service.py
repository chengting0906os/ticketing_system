"""
Kafka Configuration Service
為活動配置 Kafka topics 和 partition strategy
"""

import asyncio
import os
from typing import Dict

from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_kafka_config_service import IKafkaConfigService

from .kafka_constant_builder import KafkaTopicBuilder
from .section_based_partition_strategy import SectionBasedPartitionStrategy


class KafkaConfigService(IKafkaConfigService):
    """
    Kafka 配置服務

    負責為新活動配置:
    1. Event-specific topics
    2. Section-based partition strategy

    Note: Consumer management is handled by Docker Compose
    """

    def __init__(self, total_partitions: int = 100):
        self.total_partitions = total_partitions
        self.partition_strategy = SectionBasedPartitionStrategy(total_partitions)

    @Logger.io
    async def setup_event_infrastructure(self, *, event_id: int, seating_config: Dict) -> bool:
        """
        Setup Kafka infrastructure for new event

        Creates topics and analyzes partition distribution
        Note: Consumer management is handled by Docker Compose

        Returns:
            bool: Setup success status
        """
        try:
            Logger.base.info(f'🚀 [KAFKA] Setting up infrastructure for EVENT_ID={event_id}')

            await self._create_event_topics(event_id)
            self._analyze_partition_distribution(event_id, seating_config)

            Logger.base.info(f'✅ [KAFKA] Infrastructure setup completed for EVENT_ID={event_id}')
            return True

        except Exception as e:
            Logger.base.error(
                f'❌ [KAFKA] Failed to setup infrastructure for EVENT_ID={event_id}: {e}'
            )
            return False

    async def _create_event_topics(self, event_id: int) -> None:
        """創建 event-specific topics"""
        Logger.base.info(
            f'🎯 [KAFKA_CONFIG] Creating event-specific topics for EVENT_ID={event_id}'
        )

        topics = KafkaTopicBuilder.get_all_topics(event_id=event_id)

        # 並行創建所有 topics 以提高效率
        tasks = [self._create_single_topic(topic) for topic in topics]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 統計結果
        success_count = sum(1 for result in results if result is True)
        Logger.base.info(
            f'📊 [KAFKA_CONFIG] Created {success_count}/{len(topics)} topics successfully'
        )

    async def _create_single_topic(self, topic: str) -> bool:
        """創建單個 topic"""
        try:
            # Use full path to docker or search PATH explicitly
            docker_cmd = self._find_docker_executable()

            cmd = [
                docker_cmd,
                'exec',
                'kafka1',
                'kafka-topics',
                '--bootstrap-server',
                'kafka1:29092',
                '--create',
                '--if-not-exists',
                '--topic',
                topic,
                '--partitions',
                str(self.total_partitions),
                '--replication-factor',
                '3',
            ]

            # 使用 asyncio 執行 subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy(),  # Explicitly pass environment
            )

            _, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

            if process.returncode == 0:
                Logger.base.info(f'✅ [KAFKA_CONFIG] Created topic: {topic}')
                return True
            else:
                Logger.base.warning(
                    f'⚠️ [KAFKA_CONFIG] Failed to create topic {topic}: {stderr.decode()}'
                )
                return False

        except asyncio.TimeoutError:
            Logger.base.error(f'❌ [KAFKA_CONFIG] Timeout creating topic: {topic}')
            return False
        except Exception as e:
            Logger.base.error(f'❌ [KAFKA_CONFIG] Error creating topic {topic}: {e}')
            return False

    def _analyze_partition_distribution(self, event_id: int, seating_config: Dict) -> None:
        """分析並記錄 partition 分佈策略"""
        Logger.base.info(
            f'📊 [KAFKA_CONFIG] Analyzing partition distribution for EVENT_ID={event_id}'
        )

        # 獲取區域到 partition 的映射
        sections = seating_config.get('sections', [])
        mapping = self.partition_strategy.get_section_partition_mapping(sections, event_id)

        # 計算負載分佈
        loads = self.partition_strategy.calculate_expected_load(seating_config, event_id)

        # 記錄映射關係
        Logger.base.info('🗺️ [KAFKA_CONFIG] Subsection-to-Partition Mapping:')
        for subsection, partition in mapping.items():
            Logger.base.info(f'   {subsection} → Partition {partition}')

        # 記錄負載分佈
        Logger.base.info('⚖️ [KAFKA_CONFIG] Partition Load Distribution:')
        total_seats = 0
        for partition_id in sorted(loads.keys()):
            load_info = loads[partition_id]
            subsections_str = ', '.join(load_info['subsections'])
            seat_count = load_info['estimated_seats']
            total_seats += seat_count

            Logger.base.info(
                f'   Partition {partition_id}: {seat_count:,} seats ({subsections_str})'
            )

        Logger.base.info(f'📈 [KAFKA] Total seats: {total_seats:,}')

    def _find_docker_executable(self) -> str:
        """Find docker executable path"""
        import shutil

        docker_path = shutil.which('docker')
        if docker_path:
            return docker_path

        # Fallback to common locations
        common_paths = ['/usr/local/bin/docker', '/usr/bin/docker']
        for path in common_paths:
            if os.path.exists(path):
                return path

        return 'docker'
