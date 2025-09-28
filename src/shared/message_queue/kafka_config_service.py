"""
Kafka Configuration Service
為活動自動配置 Kafka topics 和 consumers 的服務
"""

import asyncio
from dataclasses import dataclass
import os
from typing import Dict

from src.shared.logging.loguru_io import Logger

from .kafka_constant_builder import KafkaTopicBuilder
from .section_based_partition_strategy import SectionBasedPartitionStrategy


@dataclass
class ConsumerConfig:
    name: str
    module: str
    description: str


class KafkaConfigService:
    """
    Kafka 配置服務

    負責為新創建的活動自動配置：
    1. Event-specific topics
    2. Section-based partition strategy
    3. Event-specific consumers
    """

    def __init__(self, total_partitions: int = 10):
        self.total_partitions = total_partitions
        self.partition_strategy = SectionBasedPartitionStrategy(total_partitions)

        # Consumer 配置定義
        self.consumer_configs = [
            ConsumerConfig(
                name='booking_mq_consumer',
                module='src.booking.infra.booking_mq_consumer',
                description='📚 訂單服務消費者',
            ),
            ConsumerConfig(
                name='seat_reservation_consumer',
                module='src.seat_reservation.infra.seat_reservation_consumer',
                description='🪑 座位預訂消費者',
            ),
            ConsumerConfig(
                name='event_ticketing_mq_consumer',
                module='src.event_ticketing.infra.event_ticketing_mq_consumer',
                description='🎫 票務同步消費者',
            ),
        ]

    @Logger.io
    async def setup_event_infrastructure(self, *, event_id: int, seating_config: Dict) -> bool:
        """
        為新活動設置完整的 Kafka 基礎設施

        Returns:
            bool: 是否設置成功
        """
        try:
            Logger.base.info(f'🚀 [KAFKA_CONFIG] Setting up infrastructure for EVENT_ID={event_id}')

            # 1. 創建 event-specific topics
            await self._create_event_topics(event_id)

            # 2. 分析並報告 partition 策略
            self._analyze_partition_distribution(event_id, seating_config)

            # 3. 啟動 event-specific consumers
            await self._start_event_consumers(event_id)

            Logger.base.info(
                f'✅ [KAFKA_CONFIG] Infrastructure setup completed for EVENT_ID={event_id}'
            )
            return True

        except Exception as e:
            Logger.base.error(
                f'❌ [KAFKA_CONFIG] Failed to setup infrastructure for EVENT_ID={event_id}: {e}'
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
            cmd = [
                'docker',
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
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
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
        Logger.base.info('🗺️ [KAFKA_CONFIG] Section-to-Partition Mapping:')
        for section, partition in mapping.items():
            Logger.base.info(f'   {section} 區 → Partition {partition}')

        # 記錄負載分佈
        Logger.base.info('⚖️ [KAFKA_CONFIG] Partition Load Distribution:')
        total_seats = 0
        for partition_id in sorted(loads.keys()):
            load_info = loads[partition_id]
            sections_str = ', '.join(load_info['sections'])
            seat_count = load_info['estimated_seats']
            total_seats += seat_count

            Logger.base.info(f'   Partition {partition_id}: {seat_count:,} seats ({sections_str})')

        Logger.base.info(f'📈 [KAFKA_CONFIG] Total seats: {total_seats:,}')

    async def _start_event_consumers(self, event_id: int) -> None:
        """啟動 event-specific consumers"""
        Logger.base.info(
            f'🚀 [KAFKA_CONFIG] Starting event-specific consumers for EVENT_ID={event_id}'
        )

        # 獲取項目根目錄
        project_root = self._get_project_root()

        # 並行啟動所有 consumers
        tasks = [
            self._start_single_consumer(consumer, event_id, project_root)
            for consumer in self.consumer_configs
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 統計結果
        success_count = sum(
            1 for result in results if isinstance(result, int)
        )  # PID is returned on success
        Logger.base.info(
            f'📊 [KAFKA_CONFIG] Started {success_count}/{len(self.consumer_configs)} consumers successfully'
        )

    async def _start_single_consumer(
        self, consumer: ConsumerConfig, event_id: int, project_root: str
    ) -> int:
        """啟動單個 consumer，返回 PID"""
        try:
            cmd = ['uv', 'run', 'python', '-m', consumer.module]

            # 設置環境變數
            env = os.environ.copy()
            env['EVENT_ID'] = str(event_id)
            env['PYTHONPATH'] = project_root

            # 在背景啟動程序
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=project_root,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,  # 讓程序在背景獨立運行
            )

            Logger.base.info(
                f'✅ [KAFKA_CONFIG] Started {consumer.description} for EVENT_ID={event_id}, PID={process.pid}'
            )

            return process.pid

        except Exception as e:
            Logger.base.error(
                f'❌ [KAFKA_CONFIG] Failed to start {consumer.description} for EVENT_ID={event_id}: {e}'
            )
            raise

    def _get_project_root(self) -> str:
        """獲取項目根目錄"""
        # 從當前文件位置推算項目根目錄
        current_file = os.path.abspath(__file__)
        # 從 src/shared/event_bus/kafka_config_service.py 回到根目錄
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file))))

    def get_partition_key_for_seat(
        self, section: str, subsection: int, row: int, seat: int, event_id: int
    ) -> str:
        """
        為座位生成 partition key
        使用區域集中式策略
        """
        return self.partition_strategy.generate_partition_key(
            section=section, subsection=subsection, row=row, seat=seat, event_id=event_id
        )

    async def cleanup_event_infrastructure(self, event_id: int) -> bool:
        """
        清理活動的基礎設施
        (可選功能，用於活動結束後的清理)
        """
        try:
            Logger.base.info(
                f'🧹 [KAFKA_CONFIG] Cleaning up infrastructure for EVENT_ID={event_id}'
            )

            # 1. 停止相關的 consumers (通過 PID 或進程名稱)
            # TODO: 實現 consumer 停止邏輯

            # 2. 刪除 event-specific topics (可選，取決於數據保留策略)
            # TODO: 實現 topic 刪除邏輯

            Logger.base.info(
                f'✅ [KAFKA_CONFIG] Infrastructure cleanup completed for EVENT_ID={event_id}'
            )
            return True

        except Exception as e:
            Logger.base.error(
                f'❌ [KAFKA_CONFIG] Failed to cleanup infrastructure for EVENT_ID={event_id}: {e}'
            )
            return False
