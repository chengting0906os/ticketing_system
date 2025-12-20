"""
Unit tests for partition calculation in BookingEventPublisherImpl

Tests the deterministic mapping of section/subsection to Kafka partition.
"""

from contextlib import AbstractContextManager
from typing import Any, Callable
from unittest.mock import MagicMock, patch

import pytest

from src.service.ticketing.driven_adapter.message_queue import booking_event_publisher_impl
from src.service.ticketing.driven_adapter.message_queue.booking_event_publisher_impl import (
    BookingEventPublisherImpl,
)

MockSettingsFactory = Callable[[int, int], AbstractContextManager[Any]]


@pytest.fixture
def mock_settings_factory() -> MockSettingsFactory:
    """Factory to create mock settings with custom values"""

    def _create(subsections_per_section: int, total_partitions: int) -> AbstractContextManager[Any]:
        mock = MagicMock()
        mock.SUBSECTIONS_PER_SECTION = subsections_per_section
        mock.KAFKA_TOTAL_PARTITIONS = total_partitions
        return patch.object(booking_event_publisher_impl, 'settings', mock)

    return _create


@pytest.mark.unit
class TestCalculatePartition:
    """Test partition calculation logic"""

    @pytest.mark.parametrize(
        'section,subsection,subsections_per_section,total_partitions,expected',
        [
            # Basic mapping (4 subsections, 12 partitions)
            ('A', 1, 4, 12, 0),
            ('A', 4, 4, 12, 3),
            ('B', 1, 4, 12, 4),
            ('C', 2, 4, 12, 9),
            ('D', 1, 4, 12, 0),  # wrap around: 3*4+0=12, 12%12=0
            # 100 partitions (10 subsections per section)
            ('A', 1, 10, 100, 0),
            ('A', 10, 10, 100, 9),
            ('J', 1, 10, 100, 90),
            ('J', 10, 10, 100, 99),
            ('K', 1, 10, 100, 0),  # wrap around
            # 40 subsections per section (high-density)
            ('A', 1, 40, 100, 0),
            ('A', 40, 40, 100, 39),
            ('B', 1, 40, 100, 40),
            ('C', 1, 40, 100, 80),
            ('C', 21, 40, 100, 0),  # collision with A-1
        ],
    )
    def test_partition_mapping(
        self,
        mock_settings_factory: MockSettingsFactory,
        section: str,
        subsection: int,
        subsections_per_section: int,
        total_partitions: int,
        expected: int,
    ) -> None:
        """Test partition calculation with various configurations"""
        with mock_settings_factory(subsections_per_section, total_partitions):
            result = BookingEventPublisherImpl._calculate_partition(section, subsection)
            assert result == expected

    def test_lowercase_section_is_normalized(
        self, mock_settings_factory: MockSettingsFactory
    ) -> None:
        """Lowercase section should be treated same as uppercase"""
        with mock_settings_factory(10, 100):
            upper = BookingEventPublisherImpl._calculate_partition('A', 1)
            lower = BookingEventPublisherImpl._calculate_partition('a', 1)
            assert upper == lower

    def test_deterministic_same_input_same_output(
        self, mock_settings_factory: MockSettingsFactory
    ) -> None:
        """Same input always gives same output"""
        with mock_settings_factory(10, 100):
            results = [BookingEventPublisherImpl._calculate_partition('B', 3) for _ in range(10)]
            assert all(r == results[0] for r in results)

    def test_10_sections_10_subsections_covers_all_100_partitions(
        self, mock_settings_factory: MockSettingsFactory
    ) -> None:
        """10 sections x 10 subsections = 100 unique partitions (1:1 mapping)"""
        with mock_settings_factory(10, 100):
            all_partitions = {
                BookingEventPublisherImpl._calculate_partition(section, subsection)
                for section in 'ABCDEFGHIJ'
                for subsection in range(1, 11)
            }
            assert len(all_partitions) == 100
            assert all_partitions == set(range(100))

    def test_40_subsections_causes_collisions(
        self, mock_settings_factory: MockSettingsFactory
    ) -> None:
        """With 40 subsections x sections > 100 partitions, collisions occur"""
        with mock_settings_factory(40, 100):
            # A-1 and C-21 should both map to partition 0
            a1 = BookingEventPublisherImpl._calculate_partition('A', 1)
            c21 = BookingEventPublisherImpl._calculate_partition('C', 21)
            assert a1 == c21 == 0
