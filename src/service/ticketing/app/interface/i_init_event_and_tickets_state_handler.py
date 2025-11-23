"""
Init Event And Tickets State Handler Interface

Seat initialization state handler interface - Ticketing Service responsibility
"""

from abc import ABC, abstractmethod
from typing import Dict


class IInitEventAndTicketsStateHandler(ABC):
    """
    Seat Initialization State Handler Interface

    Responsibilities:
    - Initialize all seats from seating_config to Kvrocks
    - Create event_sections index
    - Create section_stats statistics
    """

    @abstractmethod
    async def initialize_seats_from_config(self, *, event_id: int, seating_config: Dict) -> Dict:
        """
        Initialize seats from seating_config

        Args:
            event_id: Event ID
            seating_config: Seating configuration

        Returns:
            {
                'success': True/False,
                'total_seats': 3000,
                'sections_count': 30,
                'error': None or error message
            }
        """
        pass
