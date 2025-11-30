"""
Subsection-Based Partition Strategy

All seats in each subsection (A-1, A-2, B-1...) are assigned to the same partition.
Sequential mapping guarantees 1:1 correspondence with no hash collision:
- Section A-1 with 500 seats -> partition-0
- Section A-2 with 500 seats -> partition-1
- Section A-3 with 500 seats -> partition-2
- Section B-1 with 500 seats -> partition-10
...
- Section J-10 with 500 seats -> partition-99

50,000 tickets divided into 100 subsections, each subsection has its own dedicated partition.
"""

from typing import Dict

from src.platform.logging.loguru_io import Logger

from .kafka_constant_builder import PartitionKeyBuilder


class SectionBasedPartitionStrategy:
    """
    Subsection-Concentrated Partition Strategy

    Advantages:
    1. Seats in the same subsection are in the same partition, extremely high query efficiency
    2. Kvrocks State has good locality, high cache hit rate
    3. Simple seat selection logic, no cross-partition coordination needed
    4. Atomicity guarantee for seat reservations within a subsection
    5. Finer-grained partitioning improves concurrent processing capability
    """

    def __init__(self, total_partitions: int = 100) -> None:
        self.total_partitions = total_partitions
        self._subsection_partition_cache: Dict[str, int] = {}

    @Logger.io
    def get_partition_for_subsection(self, section: str, subsection: int, event_id: int) -> int:
        """
        Assign a fixed partition to the specified subsection

        Uses sequential mapping to map section-subsection combination to partition
        - A-1 → 0, A-2 → 1, ..., A-10 → 9
        - B-1 → 10, B-2 → 11, ..., B-10 → 19
        - ...
        - J-1 → 90, J-2 → 91, ..., J-10 → 99
        - Guarantees each subsection exclusively owns one partition, no collision

        Args:
            section: Section name (e.g., 'A')
            subsection: Subsection number (e.g., 1, 2, 3)
            event_id: Event ID

        Returns:
            Partition number (0 to total_partitions-1)
        """
        cache_key = f'{event_id}-{section}-{subsection}'

        if cache_key not in self._subsection_partition_cache:
            # Convert section letter to index: A=0, B=1, ..., J=9
            section_index = ord(section.upper()) - ord('A')

            # Calculate partition: section_index * 10 + (subsection - 1)
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
        self, section: str, subsection: int, row: int, seat: int, event_id: int
    ) -> str:
        """
        Generate a subsection-concentrated partition key
        Uses section-subsection combination to determine partition

        Args:
            section: Section name (e.g., 'A')
            subsection: Subsection number (e.g., 1, 2, 3)
            row: Row number (unused, but kept for interface consistency)
            seat: Seat number (unused, but kept for interface consistency)
            event_id: Event ID

        Returns:
            Partition key format: "event-{event_id}-section-{section}-{subsection}-partition-{partition}"
        """
        partition = self.get_partition_for_subsection(section, subsection, event_id)
        # Use section-subsection combination as part of the key
        section_id = f'{section}-{subsection}'
        return PartitionKeyBuilder.section_based(
            event_id=event_id, section=section_id, partition_number=partition
        )

    @Logger.io
    def get_section_partition_mapping(self, sections: list, event_id: int) -> Dict[str, int]:
        """
        Return the partition mapping for all subsections
        Used for monitoring and debugging

        Note: Now returns subsection-level mapping (e.g., "A-1" → 0)
        Compact format: subsections is an integer count
        """
        mapping = {}
        for section in sections:
            section_name = section.get('name', str(section))
            # Compact format: subsections is an integer count
            subsections_count = section.get('subsections', 1)
            for subsection_num in range(1, subsections_count + 1):
                subsection_id = f'{section_name}-{subsection_num}'
                mapping[subsection_id] = self.get_partition_for_subsection(
                    section_name, subsection_num, event_id
                )
        return mapping

    @Logger.io
    def calculate_expected_load(self, seating_config: Dict, event_id: int) -> Dict[int, Dict]:
        """
        Calculate the expected load for each partition
        Returns: {partition_id: {"subsections": [subsection_ids], "estimated_seats": count}}

        Note: Now calculates load at subsection level
        Compact format: rows/cols at top level, subsections as integer count
        """
        partition_loads = {}
        sections = seating_config.get('sections', [])

        # Compact format: rows/cols at top level
        rows = seating_config.get('rows', 10)
        cols = seating_config.get('cols', 10)
        seat_count_per_subsection = rows * cols

        for section in sections:
            section_name = section['name']

            # Compact format: subsections is an integer count
            subsections_count = section.get('subsections', 1)
            for subsection_num in range(1, subsections_count + 1):
                subsection_id = f'{section_name}-{subsection_num}'

                # Get the partition for this subsection
                partition = self.get_partition_for_subsection(
                    section_name, subsection_num, event_id
                )

                if partition not in partition_loads:
                    partition_loads[partition] = {'subsections': [], 'estimated_seats': 0}

                partition_loads[partition]['subsections'].append(subsection_id)
                partition_loads[partition]['estimated_seats'] += seat_count_per_subsection

        return partition_loads
