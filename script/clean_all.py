#!/usr/bin/env python
"""
Complete System Cleanup Script
Clear all Kafka topics, consumer groups, Kvrocks data and PostgreSQL data

Cleanup contents:
- Kafka Topics: all event-id-* topics
- Consumer Groups: all consumer groups
- Kvrocks Data: FLUSHDB to clear all key-value data
- Kvrocks State: state directories for reservation and event_ticketing
- PostgreSQL: TRUNCATE to clear all tables (ticket, booking, event, user)
"""

import os
from pathlib import Path
import shutil
import subprocess
import time

from src.platform.logging.loguru_io import Logger

COMMAND_TIMEOUT = 30
LIST_TIMEOUT = 10
RETRY_DELAY_SECONDS = 2
CONSUMER_STOP_WAIT_SECONDS = 3


class SystemCleaner:
    """Complete system cleanup utility"""

    def __init__(self):
        self.kafka_container = 'kafka1'
        self.bootstrap_server = 'kafka1:29092'
        self.project_root = Path(__file__).parent.parent
        self.kvrocks_state_dir = self.project_root / 'kvrocks_state'

    def _run_command(self, command: list, description: str = '') -> bool:
        """Execute command and return success status"""
        Logger.base.info(f'🔄 {description}')

        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=COMMAND_TIMEOUT
            )
        except subprocess.TimeoutExpired:
            Logger.base.error(f'⏰ {description} - Timeout')
            return False
        except Exception as e:
            Logger.base.error(f'❌ {description} - Error: {e}')
            return False

        if result.returncode != 0:
            Logger.base.warning(f'⚠️ {description} - Failed: {result.stderr}')
            return False

        Logger.base.info(f'✅ {description} - Success')
        return True

    def _run_kafka_command(self, args: list, timeout: int = LIST_TIMEOUT) -> subprocess.CompletedProcess | None:
        """Execute kafka command via docker and return result"""
        command = ['docker', 'exec', self.kafka_container] + args

        try:
            return subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        except Exception as e:
            Logger.base.error(f'❌ Kafka command failed: {e}')
            return None

    def _list_kafka_topics(self) -> list[str]:
        """List all user Kafka topics (excluding internal topics)"""
        result = self._run_kafka_command([
            'kafka-topics', '--bootstrap-server', self.bootstrap_server, '--list'
        ])

        if not result or result.returncode != 0:
            Logger.base.error(f'❌ Failed to list topics: {result.stderr if result else "No result"}')
            return []

        all_topics = [t.strip() for t in result.stdout.split('\n') if t.strip()]
        return [t for t in all_topics if not t.startswith('__')]

    def _list_consumer_groups(self) -> list[str]:
        """List all Kafka consumer groups"""
        result = self._run_kafka_command([
            'kafka-consumer-groups', '--bootstrap-server', self.bootstrap_server, '--list'
        ])

        if not result or result.returncode != 0:
            Logger.base.error(f'❌ Failed to list consumer groups: {result.stderr if result else "No result"}')
            return []

        return [g.strip() for g in result.stdout.split('\n') if g.strip()]

    def _delete_topic(self, topic: str) -> bool:
        """Delete a single Kafka topic"""
        return self._run_command(
            ['docker', 'exec', self.kafka_container, 'kafka-topics',
             '--bootstrap-server', self.bootstrap_server, '--delete', '--topic', topic],
            f'Deleting topic: {topic}'
        )

    def _delete_consumer_group(self, group: str, attempt: int) -> bool:
        """Delete a single consumer group"""
        return self._run_command(
            ['docker', 'exec', self.kafka_container, 'kafka-consumer-groups',
             '--bootstrap-server', self.bootstrap_server, '--delete', '--group', group],
            f'Deleting consumer group: {group} (attempt {attempt})'
        )

    def _delete_consumer_group_with_retry(self, group: str, retry_count: int) -> bool:
        """Delete consumer group with retry support"""
        for attempt in range(retry_count):
            if attempt > 0:
                Logger.base.info(f'🔄 Retry {attempt}/{retry_count - 1} for group: {group}')
                time.sleep(RETRY_DELAY_SECONDS)

            if self._delete_consumer_group(group, attempt + 1):
                return True

        Logger.base.warning(f'⚠️ Failed to delete group after {retry_count} attempts: {group}')
        return False

    def stop_all_consumers(self):
        """Stop all consumer processes - including all known and unknown consumers"""
        Logger.base.info('🛑 ==================== STOPPING CONSUMERS ====================')

        # Stop all mq_consumer processes (broad matching)
        Logger.base.info('🔍 Stopping all *mq_consumer processes...')
        self._run_command(['pkill', '-f', 'mq_consumer'], 'Stopping all mq_consumer processes')

        # Stop all start_*_consumer scripts
        Logger.base.info('🔍 Stopping start_*_consumer scripts...')
        self._run_command(['pkill', '-f', 'start_.*_consumer'], 'Stopping start_*_consumer scripts')

        # Stop topic_monitor script (important! will recreate consumer groups)
        Logger.base.info('🔍 Stopping topic_monitor script...')
        self._run_command(['pkill', '-f', 'topic_monitor'], 'Stopping topic_monitor script')

        Logger.base.info('🛑 All consumer and monitor processes stopped (broad match)')

    def clean_kafka_topics(self):
        """Clean all Kafka topics"""
        Logger.base.info('🗑️ ==================== CLEANING KAFKA TOPICS ====================')

        topics = self._list_kafka_topics()
        if not topics:
            Logger.base.info('ℹ️ No user topics found')
            return

        Logger.base.info(f'📋 Found {len(topics)} user topics to delete')

        for topic in topics:
            self._delete_topic(topic)

        Logger.base.info(f'✅ Deleted {len(topics)} topics')

    def clean_consumer_groups(self, retry_count: int = 3):
        """Clean all consumer groups - supports retry and force reset"""
        Logger.base.info('👥 ==================== CLEANING CONSUMER GROUPS ====================')

        groups = self._list_consumer_groups()
        if not groups:
            Logger.base.info('ℹ️ No consumer groups found')
            return

        Logger.base.info(f'📋 Found {len(groups)} consumer groups to delete')

        failed_groups = [g for g in groups if not self._delete_consumer_group_with_retry(g, retry_count)]

        if not failed_groups:
            Logger.base.info(f'✅ Deleted all {len(groups)} consumer groups')
            return

        Logger.base.warning(f'⚠️ {len(failed_groups)} groups could not be deleted: {failed_groups}')
        Logger.base.info('💡 Tip: Make sure all consumers are stopped and wait a few seconds')
        Logger.base.info("💡 Alternative: Restart Kafka with 'docker restart kafka1' (dev only)")

    def clean_kvrocks_data(self):
        """Flush Kvrocks data (using FLUSHDB)"""
        Logger.base.info('🗄️ ==================== FLUSHING KVROCKS DATA ====================')

        success = self._run_command(['redis-cli', '-p', '6666', 'FLUSHDB'], 'Flushing all Kvrocks data')

        if success:
            Logger.base.info('✅ Kvrocks data flushed successfully')
        else:
            Logger.base.warning('⚠️ Failed to flush Kvrocks data')

    def clean_kvrocks_state(self):
        """Clean Kvrocks state directories (reservation + event_ticketing)"""
        Logger.base.info('💾 ==================== CLEANING KVROCKS STATE ====================')

        if not self.kvrocks_state_dir.exists():
            Logger.base.info('ℹ️ Kvrocks state directory does not exist')
            return

        try:
            subdirs = [d.name for d in self.kvrocks_state_dir.iterdir() if d.is_dir()]
            Logger.base.info(f'📂 Found Kvrocks state directories: {subdirs}')
            Logger.base.info(f'🗑️ Removing Kvrocks state directory: {self.kvrocks_state_dir}')

            shutil.rmtree(self.kvrocks_state_dir)
            Logger.base.info('✅ Kvrocks state directory removed (both reservation and event_ticketing)')
        except Exception as e:
            Logger.base.error(f'❌ Failed to clean Kvrocks state: {e}')

    def clean_postgresql(self):
        """Clear all PostgreSQL database tables"""
        Logger.base.info('🐘 ==================== CLEANING POSTGRESQL ====================')

        postgres_container = os.getenv('POSTGRES_CONTAINER', 'ticketing_system_db')
        db_name = os.getenv('POSTGRES_DB', 'ticketing_system_db')
        db_user = os.getenv('POSTGRES_USER', 'postgres')

        truncate_cmd = [
            'docker', 'exec', postgres_container, 'psql',
            '-U', db_user, '-d', db_name, '-c',
            'TRUNCATE TABLE ticket, booking, event, "user" RESTART IDENTITY CASCADE;',
        ]

        success = self._run_command(truncate_cmd, 'Truncating all PostgreSQL tables')

        if success:
            Logger.base.info('✅ PostgreSQL tables truncated successfully')
        else:
            Logger.base.warning('⚠️ Failed to truncate PostgreSQL tables')

    def verify_cleanup(self):
        """Verify cleanup results"""
        Logger.base.info('🔍 ==================== VERIFICATION ====================')

        # Check remaining topics
        remaining_topics = self._list_kafka_topics()
        if remaining_topics:
            Logger.base.warning(f'⚠️ Remaining user topics: {remaining_topics}')
        else:
            Logger.base.info('✅ No user topics remaining')

        # Check remaining consumer groups
        remaining_groups = self._list_consumer_groups()
        if remaining_groups:
            Logger.base.warning(f'⚠️ Remaining consumer groups: {remaining_groups}')
        else:
            Logger.base.info('✅ No consumer groups remaining')

        # Check Kvrocks state
        if self.kvrocks_state_dir.exists():
            Logger.base.warning(f'⚠️ Kvrocks state directory still exists: {self.kvrocks_state_dir}')
        else:
            Logger.base.info('✅ Kvrocks state directory removed')

    def clean_all(self):
        """Execute complete cleanup"""
        Logger.base.info('🧹 ==================== COMPLETE SYSTEM CLEANUP ====================')
        Logger.base.info('🧹 Starting complete system cleanup...')

        self.stop_all_consumers()

        Logger.base.info(
            f'⏳ Waiting {CONSUMER_STOP_WAIT_SECONDS} seconds for consumers to fully stop...'
        )
        time.sleep(CONSUMER_STOP_WAIT_SECONDS)

        self.clean_kafka_topics()
        self.clean_consumer_groups()
        self.clean_kvrocks_data()
        self.clean_kvrocks_state()
        self.clean_postgresql()
        self.verify_cleanup()

        Logger.base.info('🧹 ==================== CLEANUP COMPLETED ====================')
        Logger.base.info('✨ System cleanup completed!')
        Logger.base.info("💡 Ready for fresh start - run 'make reset' to recreate everything")


def main():
    """Main function"""
    try:
        cleaner = SystemCleaner()
        cleaner.clean_all()
    except KeyboardInterrupt:
        Logger.base.info('🛑 Cleanup interrupted by user')
    except Exception as e:
        Logger.base.error(f'💥 Cleanup failed: {e}')


if __name__ == '__main__':
    main()
