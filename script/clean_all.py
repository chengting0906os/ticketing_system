#!/usr/bin/env python
"""
Complete System Cleanup Script
完整系統清理腳本 - 清除所有 Kafka topics, consumer groups, Kvrocks 資料和 PostgreSQL 資料

清理內容:
- Kafka Topics: 所有 event-id-* topics
- Consumer Groups: 所有 consumer groups
- Kvrocks Data: FLUSHDB 清空所有鍵值資料
- Kvrocks State: seat_reservation 和 event_ticketing 的狀態目錄
- PostgreSQL: TRUNCATE 清空所有資料表 (ticket, booking, event, user)
"""

import os
from pathlib import Path
import shutil
import subprocess

from src.platform.logging.loguru_io import Logger


class SystemCleaner:
    """系統完整清理工具"""

    def __init__(self):
        self.kafka_container = 'kafka1'
        self.bootstrap_server = 'kafka1:29092'
        self.project_root = Path(__file__).parent.parent
        self.kvrocks_state_dir = self.project_root / 'kvrocks_state'

    def run_command(self, command: list, description: str = '') -> bool:
        """執行命令"""
        try:
            Logger.base.info(f'🔄 {description}')
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                Logger.base.info(f'✅ {description} - Success')
                return True
            else:
                Logger.base.warning(f'⚠️ {description} - Failed: {result.stderr}')
                return False

        except subprocess.TimeoutExpired:
            Logger.base.error(f'⏰ {description} - Timeout')
            return False
        except Exception as e:
            Logger.base.error(f'❌ {description} - Error: {e}')
            return False

    def stop_all_consumers(self):
        """停止所有 consumer 進程 - 包含已知和未知的所有 consumer"""
        Logger.base.info('🛑 ==================== STOPPING CONSUMERS ====================')

        # 方法 1: 停止所有 mq_consumer 進程（廣泛匹配）
        Logger.base.info('🔍 Stopping all *mq_consumer processes...')
        self.run_command(['pkill', '-f', 'mq_consumer'], 'Stopping all mq_consumer processes')

        # 方法 2: 停止所有 start_*_consumer 腳本
        Logger.base.info('🔍 Stopping start_*_consumer scripts...')
        self.run_command(
            ['pkill', '-f', 'start_.*_consumer'], 'Stopping start_*_consumer scripts'
        )

        # 方法 3: 停止 topic_monitor 腳本（重要！會重新創建 consumer groups）
        Logger.base.info('🔍 Stopping topic_monitor script...')
        self.run_command(['pkill', '-f', 'topic_monitor'], 'Stopping topic_monitor script')

        Logger.base.info('🛑 All consumer and monitor processes stopped (broad match)')

    def clean_kafka_topics(self):
        """清理所有 Kafka topics"""
        Logger.base.info('🗑️ ==================== CLEANING KAFKA TOPICS ====================')

        # 列出所有 topics
        try:
            result = subprocess.run(
                [
                    'docker',
                    'exec',
                    self.kafka_container,
                    'kafka-topics',
                    '--bootstrap-server',
                    self.bootstrap_server,
                    '--list',
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                topics = [topic.strip() for topic in result.stdout.split('\n') if topic.strip()]
                user_topics = [t for t in topics if not t.startswith('__')]

                Logger.base.info(f'📋 Found {len(user_topics)} user topics to delete')

                for topic in user_topics:
                    self.run_command(
                        [
                            'docker',
                            'exec',
                            self.kafka_container,
                            'kafka-topics',
                            '--bootstrap-server',
                            self.bootstrap_server,
                            '--delete',
                            '--topic',
                            topic,
                        ],
                        f'Deleting topic: {topic}',
                    )

                Logger.base.info(f'✅ Deleted {len(user_topics)} topics')
            else:
                Logger.base.error(f'❌ Failed to list topics: {result.stderr}')

        except Exception as e:
            Logger.base.error(f'❌ Failed to clean topics: {e}')

    def clean_consumer_groups(self, retry_count=3):
        """清理所有 consumer groups - 支援重試和強制重置"""
        Logger.base.info('👥 ==================== CLEANING CONSUMER GROUPS ====================')

        try:
            result = subprocess.run(
                [
                    'docker',
                    'exec',
                    self.kafka_container,
                    'kafka-consumer-groups',
                    '--bootstrap-server',
                    self.bootstrap_server,
                    '--list',
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                groups = [group.strip() for group in result.stdout.split('\n') if group.strip()]

                Logger.base.info(f'📋 Found {len(groups)} consumer groups to delete')

                failed_groups = []

                for group in groups:
                    deleted = False

                    # 嘗試多次刪除
                    for attempt in range(retry_count):
                        if attempt > 0:
                            Logger.base.info(
                                f'🔄 Retry {attempt}/{retry_count - 1} for group: {group}'
                            )
                            import time

                            time.sleep(2)  # 等待 Kafka 釋放連接

                        # 嘗試直接刪除
                        success = self.run_command(
                            [
                                'docker',
                                'exec',
                                self.kafka_container,
                                'kafka-consumer-groups',
                                '--bootstrap-server',
                                self.bootstrap_server,
                                '--delete',
                                '--group',
                                group,
                            ],
                            f'Deleting consumer group: {group} (attempt {attempt + 1})',
                        )

                        if success:
                            deleted = True
                            break

                    if not deleted:
                        Logger.base.warning(
                            f'⚠️ Failed to delete group after {retry_count} attempts: {group}'
                        )
                        failed_groups.append(group)

                if failed_groups:
                    Logger.base.warning(
                        f'⚠️ {len(failed_groups)} groups could not be deleted: {failed_groups}'
                    )
                    Logger.base.info(
                        '💡 Tip: Make sure all consumers are stopped and wait a few seconds'
                    )
                    Logger.base.info(
                        "💡 Alternative: Restart Kafka with 'docker restart kafka1' (dev only)"
                    )
                else:
                    Logger.base.info(f'✅ Deleted all {len(groups)} consumer groups')
            else:
                Logger.base.error(f'❌ Failed to list consumer groups: {result.stderr}')

        except Exception as e:
            Logger.base.error(f'❌ Failed to clean consumer groups: {e}')

    def clean_kvrocks_data(self):
        """清空 Kvrocks 資料（使用 FLUSHDB）"""
        Logger.base.info('🗄️ ==================== FLUSHING KVROCKS DATA ====================')

        try:
            # 使用 redis-cli 連接 Kvrocks 並執行 FLUSHDB
            success = self.run_command(
                ['redis-cli', '-p', '6666', 'FLUSHDB'], 'Flushing all Kvrocks data'
            )

            if success:
                Logger.base.info('✅ Kvrocks data flushed successfully')
            else:
                Logger.base.warning('⚠️ Failed to flush Kvrocks data')

        except Exception as e:
            Logger.base.error(f'❌ Failed to flush Kvrocks: {e}')

    def clean_kvrocks_state(self):
        """清理 Kvrocks 狀態目錄 (seat_reservation + event_ticketing)"""
        Logger.base.info('💾 ==================== CLEANING KVROCKS STATE ====================')

        try:
            if self.kvrocks_state_dir.exists():
                # 列出將被清理的服務狀態
                subdirs = [d.name for d in self.kvrocks_state_dir.iterdir() if d.is_dir()]
                Logger.base.info(f'📂 Found Kvrocks state directories: {subdirs}')

                Logger.base.info(f'🗑️ Removing Kvrocks state directory: {self.kvrocks_state_dir}')
                shutil.rmtree(self.kvrocks_state_dir)
                Logger.base.info(
                    '✅ Kvrocks state directory removed (both seat_reservation and event_ticketing)'
                )
            else:
                Logger.base.info('ℹ️ Kvrocks state directory does not exist')

        except Exception as e:
            Logger.base.error(f'❌ Failed to clean Kvrocks state: {e}')

    def clean_postgresql(self):
        """清空 PostgreSQL 資料庫所有資料表"""
        Logger.base.info('🐘 ==================== CLEANING POSTGRESQL ====================')

        try:
            # 從環境變數讀取資料庫設定
            postgres_container = os.getenv('POSTGRES_CONTAINER', 'ticketing_system_db')
            db_name = os.getenv('POSTGRES_DB', 'ticketing_system_db')
            db_user = os.getenv('POSTGRES_USER', 'postgres')

            # 使用 docker exec 執行 TRUNCATE 清空所有資料表（保留結構）
            truncate_cmd = [
                'docker',
                'exec',
                postgres_container,
                'psql',
                '-U',
                db_user,
                '-d',
                db_name,
                '-c',
                'TRUNCATE TABLE ticket, booking, event, "user" RESTART IDENTITY CASCADE;',
            ]

            success = self.run_command(truncate_cmd, 'Truncating all PostgreSQL tables')

            if success:
                Logger.base.info('✅ PostgreSQL tables truncated successfully')
            else:
                Logger.base.warning('⚠️ Failed to truncate PostgreSQL tables')

        except Exception as e:
            Logger.base.error(f'❌ Failed to clean PostgreSQL: {e}')

    def verify_cleanup(self):
        """驗證清理結果"""
        Logger.base.info('🔍 ==================== VERIFICATION ====================')

        # 檢查剩餘的 topics
        try:
            result = subprocess.run(
                [
                    'docker',
                    'exec',
                    self.kafka_container,
                    'kafka-topics',
                    '--bootstrap-server',
                    self.bootstrap_server,
                    '--list',
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                topics = [topic.strip() for topic in result.stdout.split('\n') if topic.strip()]
                user_topics = [t for t in topics if not t.startswith('__')]

                if user_topics:
                    Logger.base.warning(f'⚠️ Remaining user topics: {user_topics}')
                else:
                    Logger.base.info('✅ No user topics remaining')

        except Exception as e:
            Logger.base.error(f'❌ Failed to verify topics: {e}')

        # 檢查剩餘的 consumer groups
        try:
            result = subprocess.run(
                [
                    'docker',
                    'exec',
                    self.kafka_container,
                    'kafka-consumer-groups',
                    '--bootstrap-server',
                    self.bootstrap_server,
                    '--list',
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                groups = [group.strip() for group in result.stdout.split('\n') if group.strip()]

                if groups:
                    Logger.base.warning(f'⚠️ Remaining consumer groups: {groups}')
                else:
                    Logger.base.info('✅ No consumer groups remaining')

        except Exception as e:
            Logger.base.error(f'❌ Failed to verify consumer groups: {e}')

        # 檢查 Kvrocks 狀態
        if self.kvrocks_state_dir.exists():
            Logger.base.warning(f'⚠️ Kvrocks state directory still exists: {self.kvrocks_state_dir}')
        else:
            Logger.base.info('✅ Kvrocks state directory removed')

    def clean_all(self):
        """執行完整清理"""
        import time

        Logger.base.info('🧹 ==================== COMPLETE SYSTEM CLEANUP ====================')
        Logger.base.info('🧹 Starting complete system cleanup...')

        # 步驟 1: 停止所有 consumers
        self.stop_all_consumers()

        # 等待進程完全停止和 Kafka 釋放連接
        Logger.base.info(
            '⏳ Waiting 3 seconds for consumers to fully stop and Kafka to release connections...'
        )
        time.sleep(3)

        # 步驟 2: 清理 Kafka topics
        self.clean_kafka_topics()

        # 步驟 3: 清理 consumer groups (支援重試)
        self.clean_consumer_groups()

        # 步驟 4: 清空 Kvrocks 資料
        self.clean_kvrocks_data()

        # 步驟 5: 清理 Kvrocks 狀態目錄
        self.clean_kvrocks_state()

        # 步驟 6: 清空 PostgreSQL 資料表
        self.clean_postgresql()

        # 步驟 7: 驗證清理結果
        self.verify_cleanup()

        Logger.base.info('🧹 ==================== CLEANUP COMPLETED ====================')
        Logger.base.info('✨ System cleanup completed!')
        Logger.base.info("💡 Ready for fresh start - run 'make reset' to recreate everything")


def main():
    """主函數"""
    try:
        cleaner = SystemCleaner()
        cleaner.clean_all()
    except KeyboardInterrupt:
        Logger.base.info('🛑 Cleanup interrupted by user')
    except Exception as e:
        Logger.base.error(f'💥 Cleanup failed: {e}')


if __name__ == '__main__':
    main()
