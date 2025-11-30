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
