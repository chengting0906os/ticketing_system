#!/usr/bin/env python
"""
Complete System Cleanup Script
完整系統清理腳本 - 清除所有 Kafka topics, consumer groups 和 RocksDB 狀態
"""

import subprocess
import os
import shutil
from pathlib import Path
from src.shared.logging.loguru_io import Logger


class SystemCleaner:
    """系統完整清理工具"""

    def __init__(self):
        self.kafka_container = "kafka1"
        self.bootstrap_server = "kafka1:29092"
        self.project_root = Path(__file__).parent.parent
        self.rocksdb_state_dir = self.project_root / 'rocksdb_state'

    def run_command(self, command: list, description: str = "") -> bool:
        """執行命令"""
        try:
            Logger.base.info(f"🔄 {description}")
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                Logger.base.info(f"✅ {description} - Success")
                return True
            else:
                Logger.base.warning(f"⚠️ {description} - Failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            Logger.base.error(f"⏰ {description} - Timeout")
            return False
        except Exception as e:
            Logger.base.error(f"❌ {description} - Error: {e}")
            return False

    def stop_all_consumers(self):
        """停止所有 consumer 進程"""
        Logger.base.info("🛑 ==================== STOPPING CONSUMERS ====================")

        # 停止所有可能的 consumer 進程
        consumer_patterns = [
            "python -m src.booking",
            "python -m src.seat_reservation",
            "python -m src.event_ticketing"
        ]

        for pattern in consumer_patterns:
            self.run_command(
                ["pkill", "-f", pattern],
                f"Stopping consumers matching: {pattern}"
            )

        Logger.base.info("🛑 All consumer processes stopped")

    def clean_kafka_topics(self):
        """清理所有 Kafka topics"""
        Logger.base.info("🗑️ ==================== CLEANING KAFKA TOPICS ====================")

        # 列出所有 topics
        try:
            result = subprocess.run([
                "docker", "exec", self.kafka_container,
                "kafka-topics", "--bootstrap-server", self.bootstrap_server, "--list"
            ], capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                topics = [topic.strip() for topic in result.stdout.split('\n') if topic.strip()]
                user_topics = [t for t in topics if not t.startswith('__')]

                Logger.base.info(f"📋 Found {len(user_topics)} user topics to delete")

                for topic in user_topics:
                    self.run_command([
                        "docker", "exec", self.kafka_container,
                        "kafka-topics", "--bootstrap-server", self.bootstrap_server,
                        "--delete", "--topic", topic
                    ], f"Deleting topic: {topic}")

                Logger.base.info(f"✅ Deleted {len(user_topics)} topics")
            else:
                Logger.base.error(f"❌ Failed to list topics: {result.stderr}")

        except Exception as e:
            Logger.base.error(f"❌ Failed to clean topics: {e}")

    def clean_consumer_groups(self):
        """清理所有 consumer groups"""
        Logger.base.info("👥 ==================== CLEANING CONSUMER GROUPS ====================")

        try:
            result = subprocess.run([
                "docker", "exec", self.kafka_container,
                "kafka-consumer-groups", "--bootstrap-server", self.bootstrap_server, "--list"
            ], capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                groups = [group.strip() for group in result.stdout.split('\n') if group.strip()]

                Logger.base.info(f"📋 Found {len(groups)} consumer groups to delete")

                for group in groups:
                    self.run_command([
                        "docker", "exec", self.kafka_container,
                        "kafka-consumer-groups", "--bootstrap-server", self.bootstrap_server,
                        "--delete", "--group", group
                    ], f"Deleting consumer group: {group}")

                Logger.base.info(f"✅ Deleted {len(groups)} consumer groups")
            else:
                Logger.base.error(f"❌ Failed to list consumer groups: {result.stderr}")

        except Exception as e:
            Logger.base.error(f"❌ Failed to clean consumer groups: {e}")

    def clean_rocksdb_state(self):
        """清理 RocksDB 狀態目錄"""
        Logger.base.info("💾 ==================== CLEANING ROCKSDB STATE ====================")

        try:
            if self.rocksdb_state_dir.exists():
                Logger.base.info(f"🗑️ Removing RocksDB state directory: {self.rocksdb_state_dir}")
                shutil.rmtree(self.rocksdb_state_dir)
                Logger.base.info("✅ RocksDB state directory removed")
            else:
                Logger.base.info("ℹ️ RocksDB state directory does not exist")

        except Exception as e:
            Logger.base.error(f"❌ Failed to clean RocksDB state: {e}")

    def verify_cleanup(self):
        """驗證清理結果"""
        Logger.base.info("🔍 ==================== VERIFICATION ====================")

        # 檢查剩餘的 topics
        try:
            result = subprocess.run([
                "docker", "exec", self.kafka_container,
                "kafka-topics", "--bootstrap-server", self.bootstrap_server, "--list"
            ], capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                topics = [topic.strip() for topic in result.stdout.split('\n') if topic.strip()]
                user_topics = [t for t in topics if not t.startswith('__')]

                if user_topics:
                    Logger.base.warning(f"⚠️ Remaining user topics: {user_topics}")
                else:
                    Logger.base.info("✅ No user topics remaining")

        except Exception as e:
            Logger.base.error(f"❌ Failed to verify topics: {e}")

        # 檢查剩餘的 consumer groups
        try:
            result = subprocess.run([
                "docker", "exec", self.kafka_container,
                "kafka-consumer-groups", "--bootstrap-server", self.bootstrap_server, "--list"
            ], capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                groups = [group.strip() for group in result.stdout.split('\n') if group.strip()]

                if groups:
                    Logger.base.warning(f"⚠️ Remaining consumer groups: {groups}")
                else:
                    Logger.base.info("✅ No consumer groups remaining")

        except Exception as e:
            Logger.base.error(f"❌ Failed to verify consumer groups: {e}")

        # 檢查 RocksDB 狀態
        if self.rocksdb_state_dir.exists():
            Logger.base.warning(f"⚠️ RocksDB state directory still exists: {self.rocksdb_state_dir}")
        else:
            Logger.base.info("✅ RocksDB state directory removed")

    def clean_all(self):
        """執行完整清理"""
        Logger.base.info("🧹 ==================== COMPLETE SYSTEM CLEANUP ====================")
        Logger.base.info("🧹 Starting complete system cleanup...")

        # 步驟 1: 停止所有 consumers
        self.stop_all_consumers()

        # 步驟 2: 清理 Kafka topics
        self.clean_kafka_topics()

        # 步驟 3: 清理 consumer groups
        self.clean_consumer_groups()

        # 步驟 4: 清理 RocksDB 狀態
        self.clean_rocksdb_state()

        # 步驟 5: 驗證清理結果
        self.verify_cleanup()

        Logger.base.info("🧹 ==================== CLEANUP COMPLETED ====================")
        Logger.base.info("✨ System cleanup completed!")
        Logger.base.info("💡 Ready for fresh start - run 'make reset' to recreate everything")


def main():
    """主函數"""
    try:
        cleaner = SystemCleaner()
        cleaner.clean_all()
    except KeyboardInterrupt:
        Logger.base.info("🛑 Cleanup interrupted by user")
    except Exception as e:
        Logger.base.error(f"💥 Cleanup failed: {e}")


if __name__ == "__main__":
    main()