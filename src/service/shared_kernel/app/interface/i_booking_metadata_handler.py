"""
Booking Metadata Handler Interface

Interface for managing booking metadata in Kvrocks.
Used to temporarily store booking information during reservation process.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional


class IBookingMetadataHandler(ABC):
    """
    Port (interface) for managing booking metadata in Kvrocks.

    Responsibilities:
    - Store temporary booking metadata during reservation
    - Retrieve booking metadata for reservation processing
    - Update booking status (PENDING_RESERVATION → COMPLETED/FAILED)
    - Clean up metadata after processing
    """

    @abstractmethod
    async def save_booking_metadata(
        self,
        *,
        booking_id: str,
        buyer_id: int,
        event_id: int,
        section: str,
        subsection: int,
        quantity: int,
        seat_selection_mode: str,
        seat_positions: list[str],
    ) -> None:
        """
        Save booking metadata to Kvrocks.

        Args:
            booking_id: UUID7 booking identifier
            buyer_id: Buyer user ID
            event_id: Event ID
            section: Section identifier
            subsection: Subsection number
            quantity: Number of seats to reserve
            seat_selection_mode: 'manual' or 'best_available'
            seat_positions: List of seat positions (for manual mode)

        Raises:
            StateError: If save operation fails
        """
        pass

    @abstractmethod
    async def get_booking_metadata(self, *, booking_id: str) -> Optional[Dict]:
        """
        Get booking metadata from Kvrocks.

        Args:
            booking_id: UUID7 booking identifier

        Returns:
            Booking metadata dict or None if not found

        Example:
            {
                'booking_id': 'uuid7-string',
                'buyer_id': '123',
                'event_id': '1',
                'section': 'A',
                'subsection': '1',
                'quantity': '2',
                'seat_selection_mode': 'best_available',
                'seat_positions': '[]',
                'status': 'PENDING_RESERVATION',
                'created_at': '2025-01-01T00:00:00Z'
            }
        """
        pass

    @abstractmethod
    async def update_booking_status(
        self, *, booking_id: str, status: str, error_message: str = ''
    ) -> None:
        """
        Update booking status in Kvrocks.

        Args:
            booking_id: UUID7 booking identifier
            status: New status (COMPLETED, FAILED)
            error_message: Error message if status is FAILED

        Raises:
            StateError: If update operation fails
        """
        pass

    @abstractmethod
    async def delete_booking_metadata(self, *, booking_id: str) -> None:
        """
        Delete booking metadata from Kvrocks.

        Args:
            booking_id: UUID7 booking identifier

        Note:
            Usually called after successful reservation to clean up temporary data
        """
        pass
