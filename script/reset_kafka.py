#!/usr/bin/env python
"""
Kafka Reset Script
清空所有 Kafka topics 和 consumer groups

功能：
- 刪除非 event-id-1 的 topics
- 刪除非 event-id-1 的 consumer groups
- 保護 event-id-1 相關資源（用於開發環境）

注意：此腳本不會影響 Kvrocks 狀態（seat_reservation 和 event_ticketing）
"""

import subprocess
import time
from typing import List

from src.platform.logging.loguru_io import Logger


class KafkaReset:
    """Kafka 重置工具"""

    def __init__(self):
        self.kafka_container = 'kafka1'
        self.bootstrap_server = 'kafka1:29092'
        self.in_container = self._check_if_in_container()

        env_type = 'Docker Container' if self.in_container else 'Host Machine'
        Logger.base.info(f'🔍 [Kafka Reset] Running in: {env_type}')

    def _check_if_in_container(self) -> bool:
        """檢測是否在 Docker 容器內執行"""
        import os
        import shutil

        # 方法 1: 檢查 /.dockerenv 檔案
        if os.path.exists('/.dockerenv'):
            return True

        # 方法 2: 檢查是否有 docker 命令
        if shutil.which('docker') is None:
            return True

        return False

    def run_kafka_command(self, command: List[str]) -> bool:
        """執行 Kafka 命令（自動偵測環境）"""
        if self.in_container:
            # 容器內：直接執行 Kafka 命令
            full_command = command
        else:
            # 宿主機：透過 docker exec 執行
            full_command = ['docker', 'exec', self.kafka_container] + command

        try:
            result = subprocess.run(full_command, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                return True
            else:
                Logger.base.warning(f'Command failed: {" ".join(command)}')
                Logger.base.warning(f'Error: {result.stderr}')
                return False

        except subprocess.TimeoutExpired:
            Logger.base.error(f'Command timeout: {" ".join(command)}')
            return False
        except Exception as e:
            Logger.base.error(f'Command error: {e}')
            return False

    def list_topics(self) -> List[str]:
        """列出所有 topics"""
        command = ['kafka-topics', '--bootstrap-server', self.bootstrap_server, '--list']

        if self.in_container:
            full_command = command
        else:
            full_command = ['docker', 'exec', self.kafka_container] + command

        try:
            result = subprocess.run(full_command, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                topics = [topic.strip() for topic in result.stdout.split('\n') if topic.strip()]
                user_topics = [t for t in topics if not t.startswith('__')]
                return user_topics
            else:
                Logger.base.error(f'Failed to list topics: {result.stderr}')
                return []

        except Exception as e:
            Logger.base.error(f'Error listing topics: {e}')
            return []

    def delete_topic(self, topic: str) -> bool:
        """刪除指定 topic"""
        # 保護包含 "event-id-1" 的 topics
        if 'event-id-1' in topic:
            Logger.base.info(f'🛡️ Protecting topic: {topic} (contains event-id-1)')
            return True

        command = [
            'kafka-topics',
            '--bootstrap-server',
            self.bootstrap_server,
            '--delete',
            '--topic',
            topic,
        ]

        Logger.base.info(f'🗑️ Deleting topic: {topic}')
        return self.run_kafka_command(command)

    def list_consumer_groups(self) -> List[str]:
        """列出所有 consumer groups"""
        command = ['kafka-consumer-groups', '--bootstrap-server', self.bootstrap_server, '--list']

        if self.in_container:
            full_command = command
        else:
            full_command = ['docker', 'exec', self.kafka_container] + command

        try:
            result = subprocess.run(full_command, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                groups = [group.strip() for group in result.stdout.split('\n') if group.strip()]
                return groups
            else:
                Logger.base.error(f'Failed to list consumer groups: {result.stderr}')
                return []

        except Exception as e:
            Logger.base.error(f'Error listing consumer groups: {e}')
            return []

    def get_consumer_group_state(self, group: str) -> str:
        """獲取 consumer group 的狀態"""
        command = [
            'kafka-consumer-groups',
            '--bootstrap-server',
            self.bootstrap_server,
            '--describe',
            '--group',
            group,
        ]

        if self.in_container:
            full_command = command
        else:
            full_command = ['docker', 'exec', self.kafka_container] + command

        try:
            result = subprocess.run(full_command, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                output = result.stdout
                # 檢查是否有 active consumers (CONSUMER-ID 欄位有值)
                lines = output.strip().split('\n')
                if len(lines) > 1:  # 有 header + data
                    # 如果有任何行包含 CONSUMER-ID（不是空的 "-"），表示有 active members
                    for line in lines[1:]:  # 跳過 header
                        columns = line.split()
                        if len(columns) >= 7:  # 確保有足夠的欄位
                            consumer_id = columns[6] if len(columns) > 6 else '-'
                            if consumer_id != '-':
                                return 'STABLE'  # 有 active members
                return 'EMPTY'
            else:
                return 'UNKNOWN'

        except Exception as e:
            Logger.base.warning(f'Error checking group state: {e}')
            return 'UNKNOWN'

    def delete_consumer_group(self, group: str) -> bool:
        """刪除指定 consumer group"""
        # 保護包含 "event-id-1" 的 consumer groups
        if 'event-id-1' in group:
            Logger.base.info(f'🛡️ Protecting consumer group: {group} (contains event-id-1)')
            return True

        # 檢查 group 狀態
        state = self.get_consumer_group_state(group)
        if state == 'STABLE':
            Logger.base.warning(
                f'⚠️ Cannot delete {group}: has active members (state: STABLE)\n'
                f'   💡 Tip: Stop all consumers first with "docker-compose down"'
            )
            return False

        command = [
            'kafka-consumer-groups',
            '--bootstrap-server',
            self.bootstrap_server,
            '--delete',
            '--group',
            group,
        ]

        Logger.base.info(f'🗑️ Deleting consumer group: {group}')
        return self.run_kafka_command(command)

    def reset_all(self):
        """完整重置 Kafka"""
        Logger.base.info('🚀 Starting Kafka reset...')

        # 1. 列出並刪除所有 topics
        Logger.base.info('📋 Listing topics...')
        topics = self.list_topics()

        if topics:
            # 分離受保護的和需要刪除的 topics
            protected_topics = [t for t in topics if 'event-id-1' in t]
            deletable_topics = [t for t in topics if 'event-id-1' not in t]

            Logger.base.info(f'Found {len(topics)} total topics')
            if protected_topics:
                Logger.base.info(f'🛡️ Protected topics (event-id-1): {len(protected_topics)}')
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

        # 等待一下讓 topics 完全刪除
        time.sleep(2)

        # 2. 列出並刪除所有 consumer groups
        Logger.base.info('👥 Listing consumer groups...')
        groups = self.list_consumer_groups()

        if groups:
            # 分離受保護的和需要刪除的 groups
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

        # 3. 驗證清理結果
        Logger.base.info('🔍 Verifying cleanup...')
        remaining_topics = self.list_topics()
        remaining_groups = self.list_consumer_groups()

        # 分離受保護的和不應該存在的 topics 和 groups
        protected_topics = [t for t in remaining_topics if 'event-id-1' in t]
        unexpected_topics = [t for t in remaining_topics if 'event-id-1' not in t]

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
    """主函數"""
    reset_tool = KafkaReset()
    reset_tool.reset_all()


if __name__ == '__main__':
    main()
