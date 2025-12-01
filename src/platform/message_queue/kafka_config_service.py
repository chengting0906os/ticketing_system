"""
Kafka Configuration Service
Configures Kafka topics and partition strategy for events
"""

import socket
from typing import Dict

from confluent_kafka import KafkaException
from confluent_kafka.admin import AdminClient, NewTopic

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_kafka_config_service import IKafkaConfigService

from .kafka_constant_builder import KafkaTopicBuilder
from .section_based_partition_strategy import SectionBasedPartitionStrategy


class KafkaConfigService(IKafkaConfigService):
    """
    Kafka Configuration Service (uses AdminClient API)

    Responsible for configuring new events:
    1. Event-specific topics
    2. Section-based partition strategy

    Note: Consumer management is handled by Docker Compose
    """

    def __init__(
        self,
        *,
        total_partitions: int = 100,
        bootstrap_servers: str | None = None,
    ) -> None:
        self.total_partitions = total_partitions
        self.bootstrap_servers = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS
        self.partition_strategy = SectionBasedPartitionStrategy(total_partitions)
        self._admin_client: AdminClient | None = None
        self._kafka_reachable: bool | None = None

    def _can_resolve_kafka_hosts(self) -> bool:
        """Check if Kafka hostnames can be resolved (without creating AdminClient)"""
        # Extract first host from bootstrap servers (e.g., "kafka1:29092,kafka2:29092")
        first_broker = self.bootstrap_servers.split(',')[0]
        host = first_broker.split(':')[0]

        try:
            socket.gethostbyname(host)
            return True
        except socket.gaierror:
            return False

    @property
    def admin_client(self) -> AdminClient | None:
        if self._admin_client is None:
            self._admin_client = AdminClient({'bootstrap.servers': self.bootstrap_servers})
        return self._admin_client

    def _is_kafka_available(self) -> bool:
        """Check if Kafka is reachable (with DNS pre-check to avoid ugly librdkafka errors)"""
        # Cache the result
        if self._kafka_reachable is not None:
            return self._kafka_reachable

        # First check if we can even resolve the hostname
        if not self._can_resolve_kafka_hosts():
            self._kafka_reachable = False
            return False

        # Then try actual connection
        try:
            self.admin_client.list_topics(timeout=2)
            self._kafka_reachable = True
            return True
        except Exception:
            self._kafka_reachable = False
            return False

    @Logger.io
    async def setup_event_infrastructure(self, *, event_id: int, seating_config: Dict) -> bool:
        """
        Setup Kafka infrastructure for new event

        Creates topics and analyzes partition distribution
        Note: Consumer management is handled by Docker Compose

        Returns:
            bool: Setup success status
        """
        # Quick check if Kafka is available (skip if not reachable)
        if not self._is_kafka_available():
            Logger.base.warning(
                f'⚠️ [KAFKA] Kafka not available, skipping topic creation for EVENT_ID={event_id}. '
                f'Topics will be created when consumers start.'
            )
            self._analyze_partition_distribution(event_id, seating_config)
            return True  # Not a failure - topics will be created on consumer startup

        try:
            self._create_event_topics(event_id)
            self._analyze_partition_distribution(event_id, seating_config)
            Logger.base.info(f'✅ [KAFKA] Infrastructure setup completed for EVENT_ID={event_id}')
            return True

        except Exception as e:
            Logger.base.error(
                f'❌ [KAFKA] Failed to setup infrastructure for EVENT_ID={event_id}: {e}'
            )
            return False

    def _create_event_topics(self, event_id: int) -> None:
        """Create all topics for an event using AdminClient API"""
        topics = KafkaTopicBuilder.get_all_topics(event_id=event_id)

        # Check which topics already exist
        try:
            existing_topics = set(self.admin_client.list_topics(timeout=10).topics.keys())
            topics_to_create = [topic for topic in topics if topic not in existing_topics]
        except Exception as e:
            Logger.base.warning(f'⚠️ [KAFKA_CONFIG] Could not list topics: {e}')
            topics_to_create = topics

        if not topics_to_create:
            Logger.base.info(
                f'✅ [KAFKA_CONFIG] All {len(topics)} topics already exist for EVENT_ID={event_id}'
            )
            return

        Logger.base.info(
            f'📝 [KAFKA_CONFIG] Creating {len(topics_to_create)}/{len(topics)} missing topics...'
        )

        # Create NewTopic objects
        new_topics = [
            NewTopic(
                topic=topic,
                num_partitions=self.total_partitions,
                replication_factor=3,
                config={
                    'cleanup.policy': 'delete',
                    'retention.ms': '604800000',  # 7 days
                },
            )
            for topic in topics_to_create
        ]

        # Create topics (returns dict of futures)
        futures = self.admin_client.create_topics(new_topics, request_timeout=30)

        # Wait for all futures to complete
        success_count = 0
        for topic, future in futures.items():
            try:
                future.result()  # Block until topic is created
                Logger.base.info(f'✅ [KAFKA_CONFIG] Created topic: {topic}')
                success_count += 1
            except KafkaException as e:
                # Topic might already exist from another service starting simultaneously
                if e.args[0].code() == 36:  # TopicExistsException
                    Logger.base.info(f'ℹ️  [KAFKA_CONFIG] Topic already exists: {topic}')
                    success_count += 1
                else:
                    Logger.base.error(f'❌ [KAFKA_CONFIG] Failed to create {topic}: {e}')

        Logger.base.info(
            f'📊 [KAFKA_CONFIG] Created {success_count}/{len(topics_to_create)} topics successfully'
        )

    def _analyze_partition_distribution(self, event_id: int, seating_config: Dict) -> None:
        """Analyze and log partition distribution for the event"""
        sections = seating_config.get('sections', [])
        mapping = self.partition_strategy.get_section_partition_mapping(sections, event_id)
        loads = self.partition_strategy.calculate_expected_load(seating_config, event_id)

        # Log mapping relationships
        Logger.base.info('🗺️ [KAFKA_CONFIG] Subsection-to-Partition Mapping:')
        for subsection, partition in mapping.items():
            Logger.base.info(f'   {subsection} → Partition {partition}')

        # Log load distribution
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
