"""
Unit tests for SectionBasedPartitionStrategy (Subsection-based partitioning)

Tests core behaviors of subsection partition strategy
"""

import pytest

from src.platform.message_queue.section_based_partition_strategy import (
    SectionBasedPartitionStrategy,
)


@pytest.mark.unit
class TestSubsectionBasedPartitioning:
    """Tests for subsection-level partition strategy"""

    @pytest.fixture
    def strategy(self) -> SectionBasedPartitionStrategy:
        """Create a strategy instance with 100 partitions"""
        return SectionBasedPartitionStrategy(total_partitions=100)

    def test_different_subsections_get_different_partitions(
        self, strategy: SectionBasedPartitionStrategy
    ) -> None:
        """
        Test: Different subsections within same section should get different partitions

        Given: Three subsections A-1, A-2, A-3
        When: Get partition assignments
        Then: Should be assigned to different partitions
        """
        event_id = 1

        # When: Get partitions for three subsections
        partition_a1 = strategy.get_partition_for_subsection('A', 1, event_id)
        partition_a2 = strategy.get_partition_for_subsection('A', 2, event_id)
        partition_a3 = strategy.get_partition_for_subsection('A', 3, event_id)

        # Then: Should all be different
        partitions = [partition_a1, partition_a2, partition_a3]
        assert len(set(partitions)) == 3, f'Expected 3 different partitions, got {partitions}'

        # And all should be within valid range
        for partition in partitions:
            assert 0 <= partition < 100, f'Partition {partition} out of range [0, 100)'

    def test_partition_key_includes_subsection_info(
        self, strategy: SectionBasedPartitionStrategy
    ) -> None:
        """
        Test: Generated partition key should include subsection information

        Given: Two different subsections A-1 and A-2
        When: Generate partition keys
        Then: Keys should contain subsection info and be different
        """
        event_id = 1

        # When: Generate partition keys for two different subsections
        key_a1 = strategy.generate_partition_key('A', 1, row=1, seat=1, event_id=event_id)
        key_a2 = strategy.generate_partition_key('A', 2, row=1, seat=1, event_id=event_id)

        # Then: Keys should contain subsection information
        assert 'A-1' in key_a1, f'Key should contain "A-1", got {key_a1}'
        assert 'A-2' in key_a2, f'Key should contain "A-2", got {key_a2}'

        # And the two keys should be different
        assert key_a1 != key_a2, 'Different subsections should have different partition keys'

        # Key format should match expected pattern
        assert key_a1.startswith('event-1-section-A-1-partition-')
        assert key_a2.startswith('event-1-section-A-2-partition-')

    def test_50k_config_uses_100_partitions_exactly(
        self, strategy: SectionBasedPartitionStrategy
    ) -> None:
        """
        Test: 50k config (10 sections × 10 subsections) should use exactly 100 partitions

        Given: 50k seating config with 10 subsections per section
        When: Calculate partition distribution
        Then: Should use exactly 100 partitions (1:1 mapping)
        """
        event_id = 1
        subsections_per_section = 10

        # When: Get all partition assignments
        partitions = set()
        for section_idx in range(10):  # A-J
            section = chr(ord('A') + section_idx)
            for subsection in range(1, subsections_per_section + 1):
                partition = strategy.get_partition_for_subsection(
                    section, subsection, event_id, subsections_per_section
                )
                partitions.add(partition)

        # Then: Should have exactly 100 partitions
        assert len(partitions) == 100, f'Expected 100 partitions, got {len(partitions)}'
        assert partitions == set(range(100)), 'Should use partitions 0-99'

    def test_200k_config_uses_100_partitions_with_wrapping(
        self, strategy: SectionBasedPartitionStrategy
    ) -> None:
        """
        Test: 200k config (10 sections × 40 subsections) should use 100 partitions

        Given: 200k seating config with 40 subsections per section
        When: Calculate partition distribution
        Then: Should use exactly 100 partitions (4 subsections per partition)
        """
        event_id = 1
        subsections_per_section = 40

        # When: Get all partition assignments
        partition_counts: dict[int, int] = {}
        for section_idx in range(10):  # A-J
            section = chr(ord('A') + section_idx)
            for subsection in range(1, subsections_per_section + 1):
                partition = strategy.get_partition_for_subsection(
                    section, subsection, event_id, subsections_per_section
                )
                partition_counts[partition] = partition_counts.get(partition, 0) + 1

        # Then: Should have exactly 100 partitions
        assert len(partition_counts) == 100, f'Expected 100 partitions, got {len(partition_counts)}'

        # And each partition should have exactly 4 subsections (400 / 100 = 4)
        for partition, count in partition_counts.items():
            assert count == 4, f'Partition {partition} has {count} subsections, expected 4'

    def test_200k_partition_assignment_correctness(
        self, strategy: SectionBasedPartitionStrategy
    ) -> None:
        """
        Test: Verify specific partition assignments for 200k config

        Given: 200k config with 40 subsections per section
        When: Check specific subsection mappings
        Then: Should follow the modulo-based distribution
        """
        event_id = 1
        subsections_per_section = 40

        # A-1 → (0*40 + 0) % 100 = 0
        assert strategy.get_partition_for_subsection('A', 1, event_id, subsections_per_section) == 0
        # A-40 → (0*40 + 39) % 100 = 39
        assert (
            strategy.get_partition_for_subsection('A', 40, event_id, subsections_per_section) == 39
        )
        # B-1 → (1*40 + 0) % 100 = 40
        assert (
            strategy.get_partition_for_subsection('B', 1, event_id, subsections_per_section) == 40
        )
        # C-1 → (2*40 + 0) % 100 = 80
        assert (
            strategy.get_partition_for_subsection('C', 1, event_id, subsections_per_section) == 80
        )
        # C-21 → (2*40 + 20) % 100 = 0 (wraps around)
        assert (
            strategy.get_partition_for_subsection('C', 21, event_id, subsections_per_section) == 0
        )
        # J-40 → (9*40 + 39) % 100 = 399 % 100 = 99
        assert (
            strategy.get_partition_for_subsection('J', 40, event_id, subsections_per_section) == 99
        )
