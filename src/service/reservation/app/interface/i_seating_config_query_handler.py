"""
Seating Config Query Handler Interface

CQRS Query Side - Read seating config from Kvrocks.
"""

from abc import ABC, abstractmethod

from src.service.shared_kernel.domain.value_object.subsection_config import SubsectionConfig


class ISeatingConfigQueryHandler(ABC):
    """
    Seating Config Query Handler Interface (CQRS Query)

    Responsibility: Fetch seating config from Kvrocks
    """

    @abstractmethod
    async def get_config(self, *, event_id: int, section: str) -> SubsectionConfig:
        """
        Fetch seating config for a section.

        Reads from seating_config:{event_id} JSON in Kvrocks.
        Format: {"rows": 25, "cols": 20, "sections": [{"name": "A", "price": 3000, ...}]}

        Args:
            event_id: Event ID
            section: Section name (e.g., 'A')

        Returns:
            SubsectionConfig with rows, cols, price

        Raises:
            ValueError: If config not found
        """
        pass
