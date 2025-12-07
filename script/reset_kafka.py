#!/usr/bin/env python
"""
Kafka Reset Script
Clears all Kafka topics and consumer groups

Features:
- Only protects topics defined in KafkaTopicBuilder.get_all_topics()
- Deletes ALL other topics (including old/stale topics)
- Protects consumer groups for event-id-1

Note: This script does not affect Kvrocks state (reservation and event_ticketing)
"""

import time
from typing import List, Set

from confluent_kafka import KafkaException
from confluent_kafka.admin import AdminClient

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.kafka_constant_builder import KafkaTopicBuilder


class KafkaReset:
    """Kafka reset tool (using AdminClient API)"""

    def __init__(self, *, event_id: int = 1):
        self.bootstrap_servers = settings.KAFKA_BOOTSTRAP_SERVERS
        self.admin_client = AdminClient({'bootstrap.servers': self.bootstrap_servers})
        self.event_id = event_id
        self.protected_topics: Set[str] = set(KafkaTopicBuilder.get_all_topics(event_id=event_id))
        Logger.base.info(f'🔍 [Kafka Reset] Connected to: {self.bootstrap_servers}')

    def list_topics(self) -> List[str]:
        """List all user topics (excluding internal topics)"""
        try:
            metadata = self.admin_client.list_topics(timeout=10)
            topics = [
                topic for topic in metadata.topics.keys() if not topic.startswith('__')
            ]
            return topics
        except Exception as e:
            Logger.base.error(f'Error listing topics: {e}')
            return []

    def delete_topic(self, topic: str) -> bool:
        """Delete specified topic"""
        # Only protect topics defined in KafkaTopicBuilder
        if topic in self.protected_topics:
            Logger.base.info(f'🛡️ Protecting topic: {topic} (in KafkaTopicBuilder)')
            return True

        try:
            Logger.base.info(f'🗑️ Deleting topic: {topic}')
            futures = self.admin_client.delete_topics([topic], request_timeout=30)

            for topic_name, future in futures.items():
                try:
                    future.result()  # Block until done
                    Logger.base.info(f'✅ Deleted topic: {topic_name}')
                    return True
                except KafkaException as e:
                    Logger.base.warning(f'⚠️ Failed to delete topic {topic_name}: {e}')
                    return False

        except Exception as e:
            Logger.base.error(f'Error deleting topic {topic}: {e}')
            return False

        return True

    def list_consumer_groups(self) -> List[str]:
        """List all consumer groups"""
        try:
            future = self.admin_client.list_consumer_groups(request_timeout=10)
            result = future.result()
            groups = [group.group_id for group in result.valid]
            return groups
        except Exception as e:
            Logger.base.error(f'Error listing consumer groups: {e}')
            return []

    def delete_consumer_group(self, group: str) -> bool:
        """Delete specified consumer group"""
        # Protect consumer groups containing "event-id-1"
        if 'event-id-1' in group:
            Logger.base.info(f'🛡️ Protecting consumer group: {group} (contains event-id-1)')
            return True

        try:
            Logger.base.info(f'🗑️ Deleting consumer group: {group}')
            futures = self.admin_client.delete_consumer_groups([group], request_timeout=30)

            for group_id, future in futures.items():
                try:
                    future.result()  # Block until done
                    Logger.base.info(f'✅ Deleted consumer group: {group_id}')
                    return True
                except KafkaException as e:
                    error_code = e.args[0].code()
                    if error_code == 69:  # GROUP_NOT_EMPTY
                        Logger.base.warning(
                            f'⚠️ Cannot delete {group_id}: has active members\n'
                            f'   💡 Tip: Stop all consumers first with "docker-compose down"'
                        )
                    else:
                        Logger.base.warning(f'⚠️ Failed to delete group {group_id}: {e}')
                    return False

        except Exception as e:
            Logger.base.error(f'Error deleting consumer group {group}: {e}')
            return False

        return True

    def reset_all(self):
        """Full Kafka reset"""
        Logger.base.info('🚀 Starting Kafka reset...')

        # 1. List and delete all topics
        Logger.base.info('📋 Listing topics...')
        topics = self.list_topics()

        if topics:
            # Separate protected and deletable topics (only protect KafkaTopicBuilder topics)
            protected_topics = [t for t in topics if t in self.protected_topics]
            deletable_topics = [t for t in topics if t not in self.protected_topics]

            Logger.base.info(f'Found {len(topics)} total topics')
            if protected_topics:
                Logger.base.info(f'🛡️ Protected topics (KafkaTopicBuilder): {len(protected_topics)}')
                for topic in protected_topics:
                    Logger.base.info(f'   🔒 {topic}')

            if deletable_topics:
                Logger.base.info(f'🗑️ Topics to delete: {len(deletable_topics)}')
                for topic in deletable_topics:
                    self.delete_topic(topic)
            else:
                Logger.base.info('No deletable topics found')
        else:
            Logger.base.info('No user topics found')

        # Wait for topics to be fully deleted
        time.sleep(2)

        # 2. List and delete all consumer groups
        Logger.base.info('👥 Listing consumer groups...')
        groups = self.list_consumer_groups()

        if groups:
            # Separate protected and deletable groups
            protected_groups = [g for g in groups if 'event-id-1' in g]
            deletable_groups = [g for g in groups if 'event-id-1' not in g]

            Logger.base.info(f'Found {len(groups)} total consumer groups')
            if protected_groups:
                Logger.base.info(f'🛡️ Protected groups (event-id-1): {len(protected_groups)}')
                for group in protected_groups:
                    Logger.base.info(f'   🔒 {group}')

            if deletable_groups:
                Logger.base.info(f'🗑️ Groups to delete: {len(deletable_groups)}')
                for group in deletable_groups:
                    self.delete_consumer_group(group)
            else:
                Logger.base.info('No deletable consumer groups found')
        else:
            Logger.base.info('No consumer groups found')

        # 3. Verify cleanup results
        Logger.base.info('🔍 Verifying cleanup...')
        remaining_topics = self.list_topics()
        remaining_groups = self.list_consumer_groups()

        # Separate protected and unexpected topics/groups
        protected_topics = [t for t in remaining_topics if t in self.protected_topics]
        unexpected_topics = [t for t in remaining_topics if t not in self.protected_topics]

        protected_groups = [g for g in remaining_groups if 'event-id-1' in g]
        unexpected_groups = [g for g in remaining_groups if 'event-id-1' not in g]

        if not unexpected_topics and not unexpected_groups:
            Logger.base.info('✅ Kafka reset completed successfully!')

            if protected_topics:
                Logger.base.info(f'🛡️ Protected topics preserved: {len(protected_topics)}')
                for topic in protected_topics:
                    Logger.base.info(f'   🔒 {topic}')

            if protected_groups:
                Logger.base.info(f'🛡️ Protected consumer groups preserved: {len(protected_groups)}')
                for group in protected_groups:
                    Logger.base.info(f'   🔒 {group}')
        else:
            if unexpected_topics:
                Logger.base.warning(f'⚠️ Unexpected topics remain: {unexpected_topics}')
            if unexpected_groups:
                Logger.base.warning(f'⚠️ Unexpected consumer groups remain: {unexpected_groups}')

            if protected_topics:
                Logger.base.info(f'🛡️ Protected topics (as expected): {len(protected_topics)}')
            if protected_groups:
                Logger.base.info(f'🛡️ Protected groups (as expected): {len(protected_groups)}')


def main():
    """Main function"""
    reset_tool = KafkaReset()
    reset_tool.reset_all()


if __name__ == '__main__':
    main()
