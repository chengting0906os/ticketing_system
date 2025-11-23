"""
Seat Availability Query Handler Interface

Seat availability query handler interface - Used by ticketing service to check seat availability
before creating bookings (Fail Fast principle)
"""

from abc import ABC, abstractmethod


class ISeatAvailabilityQueryHandler(ABC):
    """
    Seat Availability Query Handler Interface

    Responsibility: Allow ticketing service to check if enough seats are available before creating booking
    This is a cross-service query interface, following the Fail Fast principle
    """

    @abstractmethod
    async def check_subsection_availability(
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
            True if enough seats available, False otherwise

        Note:
            This checks 'available' seats only, not 'reserved' or 'sold'
        """
        pass
