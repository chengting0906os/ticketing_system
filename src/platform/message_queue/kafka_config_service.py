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


class KafkaConfigService(IKafkaConfigService):
    """
    Kafka Configuration Service (uses AdminClient API)

    Responsible for configuring new events:
    1. Event-specific topics

    Note: Consumer management is handled by Docker Compose
    """

    def __init__(self) -> None:
        self.total_partitions = settings.KAFKA_TOTAL_PARTITIONS
        self.bootstrap_servers = settings.KAFKA_BOOTSTRAP_SERVERS
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
            self._analyze_partition_distribution(seating_config)
            return True  # Not a failure - topics will be created on consumer startup

        try:
            self._create_event_topics(event_id)
            self._analyze_partition_distribution(seating_config)
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
                replication_factor=settings.KAFKA_REPLICATION_FACTOR,
                config=settings.KAFKA_TOPIC_CONFIG,
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

    def _analyze_partition_distribution(self, seating_config: Dict) -> None:
        """Analyze and log partition distribution for the event"""
        sections = seating_config.get('sections', [])
        rows = seating_config.get('rows', 10)
        cols = seating_config.get('cols', 10)
        seats_per_subsection = rows * cols

        total_seats = 0
        for section in sections:
            section_name = section.get('name', str(section))
            subsections_count = section.get('subsections', 1)
            for subsection_num in range(1, subsections_count + 1):
                section_index = ord(section_name.upper()) - ord('A')
                global_index = section_index * settings.SUBSECTIONS_PER_SECTION + (
                    subsection_num - 1
                )
                partition = global_index % self.total_partitions
                total_seats += seats_per_subsection
                Logger.base.info(
                    f'   {section_name}-{subsection_num} → Partition {partition} ({seats_per_subsection} seats)'
                )

        Logger.base.info(f'📈 [KAFKA] Total seats: {total_seats:,}')
