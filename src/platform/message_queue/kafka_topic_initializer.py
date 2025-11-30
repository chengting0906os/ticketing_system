"""
Kafka Topic Initializer
Container-friendly topic creation using confluent-kafka AdminClient

This module provides auto-creation of Kafka topics during consumer startup,
ensuring topics exist before subscription to prevent UNKNOWN_TOPIC_OR_PART errors.
"""

from confluent_kafka.admin import AdminClient, NewTopic
from confluent_kafka import KafkaException

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger
from .kafka_constant_builder import KafkaTopicBuilder


class KafkaTopicInitializer:
    """
    Creates Kafka topics using AdminClient (works from inside containers).

    Unlike kafka_config_service.py which uses `docker exec` for topic creation,
    this class uses confluent-kafka's AdminClient which connects directly to
    Kafka brokers via network, making it container-friendly.
    """

    def __init__(
        self, *, bootstrap_servers: str | None = None, total_partitions: int = 100
    ) -> None:
        self.bootstrap_servers = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS
        self.total_partitions = total_partitions
        self.admin_client = AdminClient({'bootstrap.servers': self.bootstrap_servers})

    def ensure_topics_exist(self, *, event_id: int) -> bool:
        """
        Ensure all required topics for an event exist, creating them if needed.

        Returns:
            bool: True if all topics exist or were created successfully
        """
        try:
            Logger.base.info(f'🔧 [TOPIC-INIT] Ensuring topics exist for EVENT_ID={event_id}')

            # Get all required topics for this event
            required_topics = KafkaTopicBuilder.get_all_topics(event_id=event_id)

            # Check which topics already exist
            existing_topics = set(self.admin_client.list_topics(timeout=10).topics.keys())
            topics_to_create = [topic for topic in required_topics if topic not in existing_topics]

            if not topics_to_create:
                Logger.base.info(
                    f'✅ [TOPIC-INIT] All {len(required_topics)} topics already exist for EVENT_ID={event_id}'
                )
                return True

            # Create missing topics
            Logger.base.info(
                f'📝 [TOPIC-INIT] Creating {len(topics_to_create)}/{len(required_topics)} missing topics...'
            )

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
                    Logger.base.info(f'✅ [TOPIC-INIT] Created topic: {topic}')
                    success_count += 1
                except KafkaException as e:
                    # Topic might already exist from another service starting simultaneously
                    if e.args[0].code() == 36:  # TopicExistsException
                        Logger.base.info(f'ℹ️  [TOPIC-INIT] Topic already exists: {topic}')
                        success_count += 1
                    else:
                        Logger.base.error(f'❌ [TOPIC-INIT] Failed to create {topic}: {e}')

            Logger.base.info(
                f'📊 [TOPIC-INIT] Created {success_count}/{len(topics_to_create)} topics for EVENT_ID={event_id}'
            )

            return success_count == len(topics_to_create)

        except Exception as e:
            Logger.base.error(f'❌ [TOPIC-INIT] Failed to ensure topics exist: {e}')
            return False
