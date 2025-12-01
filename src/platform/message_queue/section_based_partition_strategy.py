from typing import Dict

from src.platform.logging.loguru_io import Logger

from .kafka_constant_builder import PartitionKeyBuilder


class SectionBasedPartitionStrategy:
    def __init__(self, total_partitions: int = 100) -> None:
        self.total_partitions = total_partitions
        self._subsection_partition_cache: Dict[str, int] = {}

    @Logger.io
    def get_partition_for_subsection(
        self, section: str, subsection: int, event_id: int, subsections_per_section: int = 10
    ) -> int:
        """
        - For 100 subsections (10 sections × 10): 1:1 mapping
        - For 400 subsections (10 sections × 40): 4 subsections per partition

        Args:
            section: Section name (e.g., 'A')
            subsection: Subsection number (e.g., 1, 2, 3)
            event_id: Event ID
            subsections_per_section: Number of subsections per section (default 10)

        Returns:
            Partition number (0 to total_partitions-1)
        """
        cache_key = f'{event_id}-{section}-{subsection}'

        if cache_key not in self._subsection_partition_cache:
            # Convert section letter to index: A=0, B=1, ..., J=9
            section_index = ord(section.upper()) - ord('A')
            # For 10 subsections: A-1→0, A-10→9, B-1→10, J-10→99 (1:1)
            # For 40 subsections: A-1→0, A-40→39, B-1→40, C-21→0 (4:1)
            global_index = section_index * subsections_per_section + (subsection - 1)
            partition = global_index % self.total_partitions

            self._subsection_partition_cache[cache_key] = partition
        return self._subsection_partition_cache[cache_key]

    @Logger.io
    def generate_partition_key(
        self, section: str, subsection: int, row: int, seat: int, event_id: int
    ) -> str:
        partition = self.get_partition_for_subsection(section, subsection, event_id)
        section_id = f'{section}-{subsection}'
        return PartitionKeyBuilder.section_based(
            event_id=event_id, section=section_id, partition_number=partition
        )

    @Logger.io
    def get_section_partition_mapping(self, sections: list, event_id: int) -> Dict[str, int]:
        mapping = {}
        subsections_per_section = sections[0].get('subsections', 10) if sections else 10

        for section in sections:
            section_name = section.get('name', str(section))
            subsections_count = section.get('subsections', 1)
            for subsection_num in range(1, subsections_count + 1):
                subsection_id = f'{section_name}-{subsection_num}'
                mapping[subsection_id] = self.get_partition_for_subsection(
                    section_name, subsection_num, event_id, subsections_per_section
                )
        return mapping

    @Logger.io
    def calculate_expected_load(self, seating_config: Dict, event_id: int) -> Dict[int, Dict]:
        partition_loads = {}
        sections = seating_config.get('sections', [])
        rows = seating_config.get('rows', 10)
        cols = seating_config.get('cols', 10)
        seat_count_per_subsection = rows * cols
        subsections_per_section = sections[0].get('subsections', 10) if sections else 10

        for section in sections:
            section_name = section['name']
            subsections_count = section.get('subsections', 1)
            for subsection_num in range(1, subsections_count + 1):
                subsection_id = f'{section_name}-{subsection_num}'
                partition = self.get_partition_for_subsection(
                    section_name, subsection_num, event_id, subsections_per_section
                )

                if partition not in partition_loads:
                    partition_loads[partition] = {'subsections': [], 'estimated_seats': 0}

                partition_loads[partition]['subsections'].append(subsection_id)
                partition_loads[partition]['estimated_seats'] += seat_count_per_subsection
        return partition_loads
