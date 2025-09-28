#!/usr/bin/env python
"""
Kafka Reset Script
清空所有 Kafka topics 和 consumer groups
"""

import subprocess
import time
from typing import List

from src.shared.logging.loguru_io import Logger


class KafkaReset:
    """Kafka 重置工具"""

    def __init__(self):
        self.kafka_container = "kafka1"
        self.bootstrap_server = "kafka1:29092"

    def run_kafka_command(self, command: List[str]) -> bool:
        """執行 Kafka 命令"""
        full_command = [
            "docker", "exec", self.kafka_container
        ] + command

        try:
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                return True
            else:
                Logger.base.warning(f"Command failed: {' '.join(command)}")
                Logger.base.warning(f"Error: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            Logger.base.error(f"Command timeout: {' '.join(command)}")
            return False
        except Exception as e:
            Logger.base.error(f"Command error: {e}")
            return False

    def list_topics(self) -> List[str]:
        """列出所有 topics"""
        command = [
            "kafka-topics",
            "--bootstrap-server", self.bootstrap_server,
            "--list"
        ]

        try:
            result = subprocess.run(
                ["docker", "exec", self.kafka_container] + command,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                topics = [topic.strip() for topic in result.stdout.split('\n') if topic.strip()]
                # 過濾掉 Kafka 內部 topics
                user_topics = [t for t in topics if not t.startswith('__')]
                return user_topics
            else:
                Logger.base.error(f"Failed to list topics: {result.stderr}")
                return []

        except Exception as e:
            Logger.base.error(f"Error listing topics: {e}")
            return []

    def delete_topic(self, topic: str) -> bool:
        """刪除指定 topic"""
        command = [
            "kafka-topics",
            "--bootstrap-server", self.bootstrap_server,
            "--delete",
            "--topic", topic
        ]

        Logger.base.info(f"🗑️ Deleting topic: {topic}")
        return self.run_kafka_command(command)

    def list_consumer_groups(self) -> List[str]:
        """列出所有 consumer groups"""
        command = [
            "kafka-consumer-groups",
            "--bootstrap-server", self.bootstrap_server,
            "--list"
        ]

        try:
            result = subprocess.run(
                ["docker", "exec", self.kafka_container] + command,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                groups = [group.strip() for group in result.stdout.split('\n') if group.strip()]
                return groups
            else:
                Logger.base.error(f"Failed to list consumer groups: {result.stderr}")
                return []

        except Exception as e:
            Logger.base.error(f"Error listing consumer groups: {e}")
            return []

    def delete_consumer_group(self, group: str) -> bool:
        """刪除指定 consumer group"""
        command = [
            "kafka-consumer-groups",
            "--bootstrap-server", self.bootstrap_server,
            "--delete",
            "--group", group
        ]

        Logger.base.info(f"🗑️ Deleting consumer group: {group}")
        return self.run_kafka_command(command)

    def reset_all(self):
        """完整重置 Kafka"""
        Logger.base.info("🚀 Starting Kafka reset...")

        # 1. 列出並刪除所有 topics
        Logger.base.info("📋 Listing topics...")
        topics = self.list_topics()

        if topics:
            Logger.base.info(f"Found {len(topics)} topics to delete")
            for topic in topics:
                self.delete_topic(topic)
        else:
            Logger.base.info("No user topics found")

        # 等待一下讓 topics 完全刪除
        time.sleep(2)

        # 2. 列出並刪除所有 consumer groups
        Logger.base.info("👥 Listing consumer groups...")
        groups = self.list_consumer_groups()

        if groups:
            Logger.base.info(f"Found {len(groups)} consumer groups to delete")
            for group in groups:
                self.delete_consumer_group(group)
        else:
            Logger.base.info("No consumer groups found")

        # 3. 驗證清理結果
        Logger.base.info("🔍 Verifying cleanup...")
        remaining_topics = self.list_topics()
        remaining_groups = self.list_consumer_groups()

        if not remaining_topics and not remaining_groups:
            Logger.base.info("✅ Kafka reset completed successfully!")
        else:
            if remaining_topics:
                Logger.base.warning(f"⚠️ Some topics remain: {remaining_topics}")
            if remaining_groups:
                Logger.base.warning(f"⚠️ Some consumer groups remain: {remaining_groups}")


def main():
    """主函數"""
    reset_tool = KafkaReset()
    reset_tool.reset_all()


if __name__ == "__main__":
    main()