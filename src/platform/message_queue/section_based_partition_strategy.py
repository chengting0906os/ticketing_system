"""
Subsection-Based Partition Strategy
子區域集中式 Partition 分配策略

每個子區域(A-1, A-2, B-1...)的所有座位分配到同一個 partition
使用順序映射保證 1:1 對應，無 hash collision
- A-1 區 500張 → partition-0
- A-2 區 500張 → partition-1
- A-3 區 500張 → partition-2
- B-1 區 500張 → partition-10
...
- J-10 區 500張 → partition-99

50000張票分100個subsection，每個subsection獨立一個partition
"""

from typing import Dict
from uuid import UUID

from src.platform.logging.loguru_io import Logger

from .kafka_constant_builder import PartitionKeyBuilder


class SectionBasedPartitionStrategy:
    """
    子區域集中式 Partition 策略

    優勢：
    1. 同 subsection 座位在同一 partition，查詢效率極高
    2. Kvrocks State 局部性好，cache hit rate 高
    3. 座位選擇邏輯簡單，無需跨 partition 協調
    4. Subsection 內座位預訂的原子性保證
    5. 更細粒度的分區，提升並發處理能力
    """

    def __init__(self, total_partitions: int = 100):
        self.total_partitions = total_partitions
        self._subsection_partition_cache: Dict[str, int] = {}

    @Logger.io
    def get_partition_for_subsection(self, section: str, subsection: int, event_id: UUID) -> int:
        """
        為指定子區域分配固定的 partition

        使用順序映射將 section-subsection 組合映射到 partition
        - A-1 → 0, A-2 → 1, ..., A-10 → 9
        - B-1 → 10, B-2 → 11, ..., B-10 → 19
        - ...
        - J-1 → 90, J-2 → 91, ..., J-10 → 99
        - 保證每個 subsection 獨佔一個 partition，無碰撞

        Args:
            section: 區域名稱 (e.g., 'A')
            subsection: 子區域編號 (e.g., 1, 2, 3)
            event_id: 活動 ID

        Returns:
            Partition number (0 to total_partitions-1)
        """
        cache_key = f'{event_id}-{section}-{subsection}'

        if cache_key not in self._subsection_partition_cache:
            # 將 section 字母轉換為索引：A=0, B=1, ..., J=9
            section_index = ord(section.upper()) - ord('A')

            # 計算 partition：section_index * 10 + (subsection - 1)
            # A-1 → 0*10 + 0 = 0
            # A-2 → 0*10 + 1 = 1
            # B-1 → 1*10 + 0 = 10
            # J-10 → 9*10 + 9 = 99
            partition = section_index * 10 + (subsection - 1)

            self._subsection_partition_cache[cache_key] = partition
            Logger.base.debug(f'📍 [PARTITION] {section}-{subsection} → partition-{partition}')

        return self._subsection_partition_cache[cache_key]

    @Logger.io
    def generate_partition_key(
        self, section: str, subsection: int, row: int, seat: int, event_id: UUID
    ) -> str:
        """
        生成子區域集中式的 partition key
        使用 section-subsection 組合決定 partition

        Args:
            section: 區域名稱 (e.g., 'A')
            subsection: 子區域編號 (e.g., 1, 2, 3)
            row: 排數 (未使用，但保留以保持接口一致)
            seat: 座位數 (未使用，但保留以保持接口一致)
            event_id: 活動 ID

        Returns:
            Partition key 格式: "event-{event_id}-section-{section}-{subsection}-partition-{partition}"
        """
        partition = self.get_partition_for_subsection(section, subsection, event_id)
        # 使用 section-subsection 組合作為 key 的一部分
        section_id = f'{section}-{subsection}'
        return PartitionKeyBuilder.section_based(
            event_id=event_id, section=section_id, partition_number=partition
        )

    @Logger.io
    def get_section_partition_mapping(self, sections: list, event_id: UUID) -> Dict[str, int]:
        """
        返回所有子區域的 partition 映射關係
        用於監控和調試

        Note: 現在返回的是 subsection 級別的映射 (e.g., "A-1" → 0)
        """
        mapping = {}
        for section in sections:
            section_name = section.get('name', str(section))
            # 遍歷每個 subsection
            for subsection_data in section.get('subsections', []):
                subsection_num = subsection_data.get('number', 1)
                subsection_id = f'{section_name}-{subsection_num}'
                mapping[subsection_id] = self.get_partition_for_subsection(
                    section_name, subsection_num, event_id
                )
        return mapping

    @Logger.io
    def calculate_expected_load(self, seating_config: Dict, event_id: UUID) -> Dict[int, Dict]:
        """
        計算每個 partition 的預期負載
        返回：{partition_id: {"subsections": [subsection_ids], "estimated_seats": count}}

        Note: 現在基於 subsection 級別計算負載
        """
        partition_loads = {}
        sections = seating_config.get('sections', [])

        for section in sections:
            section_name = section['name']

            # 遍歷每個 subsection
            for subsection_data in section.get('subsections', []):
                subsection_num = subsection_data.get('number', 1)
                subsection_id = f'{section_name}-{subsection_num}'

                # 獲取此 subsection 的 partition
                partition = self.get_partition_for_subsection(
                    section_name, subsection_num, event_id
                )

                # 計算該 subsection 的座位數量
                rows = subsection_data.get('rows', 0)
                seats_per_row = subsection_data.get('seats_per_row', 0)
                seat_count = rows * seats_per_row

                if partition not in partition_loads:
                    partition_loads[partition] = {'subsections': [], 'estimated_seats': 0}

                partition_loads[partition]['subsections'].append(subsection_id)
                partition_loads[partition]['estimated_seats'] += seat_count

        return partition_loads
