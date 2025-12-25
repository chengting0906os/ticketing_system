#!/usr/bin/env python
"""
Kafka Reset Script
Clears all Kafka topics and consumer groups

Features:
- Deletes topics not containing event-id-1
- Deletes consumer groups not containing event-id-1
- Protects event-id-1 related resources (for development environment)

Note: This script does not affect Kvrocks state (reservation and event_ticketing)
"""

import time

from confluent_kafka import KafkaException
from confluent_kafka.admin import AdminClient

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger

PROTECTED_PATTERN = 'event-id-1'
TOPIC_DELETE_WAIT_SECONDS = 2


class KafkaReset:
    """Kafka reset tool (using AdminClient API)"""

    def __init__(self):
        self.bootstrap_servers = settings.KAFKA_BOOTSTRAP_SERVERS
        self.admin_client = AdminClient({'bootstrap.servers': self.bootstrap_servers})
        Logger.base.info(f'🔍 [Kafka Reset] Connected to: {self.bootstrap_servers}')

    @staticmethod
    def _is_protected(name: str) -> bool:
        """Check if a topic/group name is protected"""
        return PROTECTED_PATTERN in name

    @staticmethod
    def _partition_by_protection(items: list[str]) -> tuple[list[str], list[str]]:
        """Partition items into (protected, deletable) lists"""
        protected = [item for item in items if KafkaReset._is_protected(item)]
        deletable = [item for item in items if not KafkaReset._is_protected(item)]
        return protected, deletable

    @staticmethod
    def _log_protected_items(items: list[str], item_type: str) -> None:
        """Log protected items"""
        if not items:
            return
        Logger.base.info(f'🛡️ Protected {item_type} ({PROTECTED_PATTERN}): {len(items)}')
        for item in items:
            Logger.base.info(f'   🔒 {item}')

    def list_topics(self) -> list[str]:
        """List all user topics (excluding internal topics)"""
        try:
            metadata = self.admin_client.list_topics(timeout=10)
            return [topic for topic in metadata.topics.keys() if not topic.startswith('__')]
        except Exception as e:
            Logger.base.error(f'Error listing topics: {e}')
            return []

    def list_consumer_groups(self) -> list[str]:
        """List all consumer groups"""
        try:
            future = self.admin_client.list_consumer_groups(request_timeout=10)
            result = future.result()
            return [group.group_id for group in result.valid]
        except Exception as e:
            Logger.base.error(f'Error listing consumer groups: {e}')
            return []

    def delete_topic(self, topic: str) -> bool:
        """Delete specified topic"""
        if self._is_protected(topic):
            Logger.base.info(f'🛡️ Protecting topic: {topic} (contains {PROTECTED_PATTERN})')
            return True

        Logger.base.info(f'🗑️ Deleting topic: {topic}')

        try:
            futures = self.admin_client.delete_topics([topic], request_timeout=30)
            future = futures[topic]
            future.result()
            Logger.base.info(f'✅ Deleted topic: {topic}')
            return True
        except KafkaException as e:
            Logger.base.warning(f'⚠️ Failed to delete topic {topic}: {e}')
            return False
        except Exception as e:
            Logger.base.error(f'Error deleting topic {topic}: {e}')
            return False

    def delete_consumer_group(self, group: str) -> bool:
        """Delete specified consumer group"""
        if self._is_protected(group):
            Logger.base.info(f'🛡️ Protecting consumer group: {group} (contains {PROTECTED_PATTERN})')
            return True

        Logger.base.info(f'🗑️ Deleting consumer group: {group}')

        try:
            futures = self.admin_client.delete_consumer_groups([group], request_timeout=30)
            future = futures[group]
            future.result()
            Logger.base.info(f'✅ Deleted consumer group: {group}')
            return True
        except KafkaException as e:
            error_code = e.args[0].code()
            if error_code == 69:  # GROUP_NOT_EMPTY
                Logger.base.warning(
                    f'⚠️ Cannot delete {group}: has active members\n'
                    f'   💡 Tip: Stop all consumers first with "docker-compose down"'
                )
            else:
                Logger.base.warning(f'⚠️ Failed to delete group {group}: {e}')
            return False
        except Exception as e:
            Logger.base.error(f'Error deleting consumer group {group}: {e}')
            return False

    def _delete_topics(self) -> None:
        """Delete all deletable topics"""
        Logger.base.info('📋 Listing topics...')
        topics = self.list_topics()

        if not topics:
            Logger.base.info('No user topics found')
            return

        protected, deletable = self._partition_by_protection(topics)
        Logger.base.info(f'Found {len(topics)} total topics')

        self._log_protected_items(protected, 'topics')

        if not deletable:
            Logger.base.info('No deletable topics found')
            return

        Logger.base.info(f'🗑️ Topics to delete: {len(deletable)}')
        for topic in deletable:
            self.delete_topic(topic)

    def _delete_consumer_groups(self) -> None:
        """Delete all deletable consumer groups"""
        Logger.base.info('👥 Listing consumer groups...')
        groups = self.list_consumer_groups()

        if not groups:
            Logger.base.info('No consumer groups found')
            return

        protected, deletable = self._partition_by_protection(groups)
        Logger.base.info(f'Found {len(groups)} total consumer groups')

        self._log_protected_items(protected, 'groups')

        if not deletable:
            Logger.base.info('No deletable consumer groups found')
            return

        Logger.base.info(f'🗑️ Groups to delete: {len(deletable)}')
        for group in deletable:
            self.delete_consumer_group(group)

    def _verify_cleanup(self) -> None:
        """Verify cleanup results"""
        Logger.base.info('🔍 Verifying cleanup...')

        remaining_topics = self.list_topics()
        remaining_groups = self.list_consumer_groups()

        protected_topics, unexpected_topics = self._partition_by_protection(remaining_topics)
        protected_groups, unexpected_groups = self._partition_by_protection(remaining_groups)

        if unexpected_topics or unexpected_groups:
            if unexpected_topics:
                Logger.base.warning(f'⚠️ Unexpected topics remain: {unexpected_topics}')
            if unexpected_groups:
                Logger.base.warning(f'⚠️ Unexpected consumer groups remain: {unexpected_groups}')

            self._log_protected_items(protected_topics, 'topics (as expected)')
            self._log_protected_items(protected_groups, 'groups (as expected)')
            return

        Logger.base.info('✅ Kafka reset completed successfully!')
        self._log_protected_items(protected_topics, 'topics preserved')
        self._log_protected_items(protected_groups, 'consumer groups preserved')

    def reset_all(self):
        """Full Kafka reset"""
        Logger.base.info('🚀 Starting Kafka reset...')

        self._delete_topics()
        time.sleep(TOPIC_DELETE_WAIT_SECONDS)

        self._delete_consumer_groups()
        self._verify_cleanup()


def main():
    """Main function"""
    reset_tool = KafkaReset()
    reset_tool.reset_all()


if __name__ == '__main__':
    main()
