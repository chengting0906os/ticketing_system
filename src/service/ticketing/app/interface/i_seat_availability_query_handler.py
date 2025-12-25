"""
Seat Availability Query Handler Interface

Used by ticketing service to check seat availability before creating bookings (Fail Fast principle)
"""

from abc import ABC, abstractmethod


class ISeatAvailabilityQueryHandler(ABC):
    """
    Seat Availability Query Handler Interface

    Responsibility: Quick availability check before sending to reservation service
    - No cache → pass through (optimistic)
    - Has cache → check if enough seats available
    """

    @abstractmethod
    async def check_availability(
        self, *, event_id: int, section: str, subsection: int, required_quantity: int
    ) -> bool:
        """
        Check if the specified subsection has enough available seats

        Args:
            event_id: Event ID
            section: Section code (e.g., 'A', 'B')
            subsection: Subsection number (e.g., 1, 2)
            required_quantity: Required number of seats

        Returns:
            True if enough seats available (or no cache - optimistic pass through)
            False if cache shows insufficient seats
        """
        pass
