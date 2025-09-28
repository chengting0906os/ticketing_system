"""
統一依賴注入容器
所有應用程序的服務依賴都通過這個單一容器管理

設計原則：
1. 所有服務都是 Singleton - 確保資源共享和一致性
2. 使用 dependency-injector 庫 - 成熟、穩定的 DI 解決方案
3. 單一職責 - 只負責服務的創建和生命週期管理
4. 延遲初始化 - 服務只在第一次使用時創建
5. 簡潔 API - 提供簡單的服務訪問方法
"""

from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.config.core_setting import Settings
from src.shared.message_queue.kafka_config_service import KafkaConfigService
from src.shared.message_queue.unified_mq_publisher import QuixStreamMqPublisher
from src.shared.message_queue.section_based_partition_strategy import SectionBasedPartitionStrategy
from src.booking.infra.booking_command_repo_impl import BookingCommandRepoImpl
from src.booking.infra.booking_query_repo_impl import BookingQueryRepoImpl
from src.event_ticketing.infra.event_ticketing_command_repo_impl import (
    EventTicketingCommandRepoImpl,
)
from src.event_ticketing.infra.event_ticketing_query_repo_impl import EventTicketingQueryRepoImpl
from src.shared_kernel.user.infra.user_repo_impl import UserRepoImpl
from src.shared_kernel.user.infra.user_command_repo_impl import UserCommandRepoImpl
from src.shared_kernel.user.infra.user_query_repo_impl import UserQueryRepoImpl


class Container(containers.DeclarativeContainer):
    """應用程序的統一依賴注入容器 - 所有服務的單一真實來源"""

    # === 配置服務 ===
    config_service = providers.Singleton(Settings)

    # === 基礎設施服務 (Singleton) ===

    # Kafka 配置服務 - 事件驅動架構的核心
    kafka_service = providers.Singleton(KafkaConfigService)

    # 統一消息發布者 - 跨服務事件通信
    mq_publisher = providers.Singleton(QuixStreamMqPublisher)

    # 日誌服務已移除 - 直接使用 Logger 静态类

    # === 領域服務 ===

    # 分區策略服務
    partition_strategy = providers.Singleton(SectionBasedPartitionStrategy)

    # === 仓储服务 (Singleton - 共享实例) ===

    # Booking 命令仓储
    booking_command_repo = providers.Singleton(BookingCommandRepoImpl)

    # Booking 查询仓储
    booking_query_repo = providers.Singleton(BookingQueryRepoImpl)

    # EventTicketing 統一命令仓储 - 新的聚合根倉儲
    event_ticketing_command_repo = providers.Singleton(EventTicketingCommandRepoImpl)

    # EventTicketing 統一查询仓储 - 新的聚合根倉儲
    event_ticketing_query_repo = providers.Singleton(EventTicketingQueryRepoImpl)

    # User 仓储
    user_repo = providers.Singleton(UserRepoImpl)

    # User 命令仓储
    user_command_repo = providers.Singleton(UserCommandRepoImpl)

    # User 查询仓储
    user_query_repo = providers.Singleton(UserQueryRepoImpl)

    # === 未來擴展服務 ===
    # Redis 緩存、認證、郵件等服務可在此處添加


# 全局容器實例 - 應用程序的單一依賴注入點
container = Container()


# Services are accessed directly via Container.service_name in @inject + Provide pattern
# No convenience functions needed


# === 生命週期管理 ===


def setup():
    """
    設置依賴容器
    在應用程序啟動時調用，確保所有必要的服務都已初始化
    """
    # 預加載關鍵基礎設施服務以確保啟動時發現配置問題
    container.kafka_service()
    container.config_service()
    container.mq_publisher()
    container.partition_strategy()


def cleanup():
    """
    清理依賴容器
    在應用程序關閉時調用，正確清理所有單例實例
    """
    container.reset_singletons()


# === Use Case 依賴創建 ===


def create_use_case_dependencies(session: AsyncSession) -> dict:
    """
    為 Use Case 創建統一的依賴字典
    這確保了所有 Use Case 使用相同的服務實例

    Args:
        session: 數據庫會話（通常是 scoped，不是 singleton）

    Returns:
        包含所有 Use Case 可能需要的依賴的字典
    """
    return {
        # 基础设施服务 (Singleton)
        'kafka_service': container.kafka_service(),
        'config_service': container.config_service(),
        'mq_publisher': container.mq_publisher(),
        'partition_strategy': container.partition_strategy(),
        'session': session,
        # 仓储服务 (Singleton - 共享实例)
        'booking_command_repo': container.booking_command_repo(),
        'booking_query_repo': container.booking_query_repo(),
        'event_ticketing_command_repo': container.event_ticketing_command_repo(),
        'event_ticketing_query_repo': container.event_ticketing_query_repo(),
    }
