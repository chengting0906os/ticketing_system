"""
Section-Based Partition Strategy
區域集中式 Partition 分配策略

每個區域(A,B,C...)的所有座位分配到同一個 partition
- A區 5000張 → partition-0
- B區 5000張 → partition-1
- C區 5000張 → partition-2
...
"""

import hashlib
from typing import Dict

from src.shared.logging.loguru_io import Logger

from .kafka_constant_builder import PartitionKeyBuilder


class SectionBasedPartitionStrategy:
    """
    區域集中式 Partition 策略

    優勢：
    1. 同區域座位在同一 partition，查詢效率極高
    2. RocksDB State 局部性好，cache hit rate 高
    3. 座位選擇邏輯簡單，無需跨 partition 協調
    4. 區域內座位預訂的原子性保證
    """

    def __init__(self, total_partitions: int = 10):
        self.total_partitions = total_partitions
        self._section_partition_cache: Dict[str, int] = {}

    @Logger.io
    def get_partition_for_section(self, section: str, event_id: int) -> int:
        """
        為指定區域分配固定的 partition

        使用字母順序映射：A→0, B→1, C→2, D→3, E→4...
        - 相同區域永遠分配到相同 partition
        - 簡單直觀的映射關係，便於調試和監控
        """
        cache_key = f'{event_id}-{section}'

        if cache_key not in self._section_partition_cache:
            # 使用字母順序直接映射到 partition
            # A→0, B→1, C→2, D→3, E→4, F→5, G→6, H→7, I→8, J→9
            if len(section) == 1 and section.isalpha():
                # 單字母區域：直接使用字母順序
                partition = ord(section.upper()) - ord('A')
                partition = partition % self.total_partitions
            else:
                # 非單字母區域：使用哈希（向後兼容）
                hash_input = f'{event_id}-{section}'
                section_hash = hashlib.md5(hash_input.encode()).hexdigest()
                partition = int(section_hash[:8], 16) % self.total_partitions

            self._section_partition_cache[cache_key] = partition

        return self._section_partition_cache[cache_key]

    @Logger.io
    def generate_partition_key(
        self, section: str, subsection: int, row: int, seat: int, event_id: int
    ) -> str:
        """
        生成區域集中式的 partition key
        使用統一的 PartitionKeyBuilder
        """
        partition = self.get_partition_for_section(section, event_id)
        return PartitionKeyBuilder.section_based(
            event_id=event_id, section=section, partition_number=partition
        )

    @Logger.io
    def get_section_partition_mapping(self, sections: list, event_id: int) -> Dict[str, int]:
        """
        返回所有區域的 partition 映射關係
        用於監控和調試
        """
        mapping = {}
        for section in sections:
            section_name = section.get('name', str(section))
            mapping[section_name] = self.get_partition_for_section(section_name, event_id)
        return mapping

    @Logger.io
    def calculate_expected_load(self, seating_config: Dict, event_id: int) -> Dict[int, Dict]:
        """
        計算每個 partition 的預期負載
        返回：{partition_id: {"sections": [section_names], "estimated_seats": count}}
        """
        partition_loads = {}
        sections = seating_config.get('sections', [])

        for section in sections:
            section_name = section['name']
            partition = self.get_partition_for_section(section_name, event_id)

            # 計算該區域的座位數量
            seat_count = 0
            for subsection in section.get('subsections', []):
                rows = subsection.get('rows', 0)
                seats_per_row = subsection.get('seats_per_row', 0)
                seat_count += rows * seats_per_row

            if partition not in partition_loads:
                partition_loads[partition] = {'sections': [], 'estimated_seats': 0}

            partition_loads[partition]['sections'].append(section_name)
            partition_loads[partition]['estimated_seats'] += seat_count

        return partition_loads
