from abc import ABC, abstractmethod
from typing import Dict, List


class KafkaConfigServiceInterface(ABC):
    """
    Kafka 配置服務抽象接口

    定義了 Kafka 基礎設施管理的核心契約
    """

    @abstractmethod
    async def setup_event_infrastructure(self, *, event_id: int, seating_config: Dict) -> bool:
        """
        為新活動設置完整的 Kafka 基礎設施

        Args:
            event_id: 活動ID
            seating_config: 座位配置

        Returns:
            bool: 是否設置成功
        """
        ...

    @abstractmethod
    def get_partition_key_for_seat(
        self, section: str, subsection: int, row: int, seat: int, event_id: int
    ) -> str:
        """
        為座位生成 partition key
        使用區域集中式策略

        Args:
            section: 區域名稱
            subsection: 子區域編號
            row: 排數
            seat: 座位數
            event_id: 活動ID

        Returns:
            str: partition key
        """
        ...

    @abstractmethod
    async def get_active_consumer_groups(self) -> List[str]:
        """
        獲取所有活躍的 consumer groups

        Returns:
            List[str]: 活躍的 consumer group 列表
        """
        ...

    @abstractmethod
    async def cleanup_event_infrastructure(self, event_id: int) -> bool:
        """
        清理活動的基礎設施
        (可選功能，用於活動結束後的清理)

        Args:
            event_id: 活動ID

        Returns:
            bool: 是否清理成功
        """
        ...
