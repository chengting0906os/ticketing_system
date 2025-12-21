"""
Booking Command Repository Interface (Ticketing Service)

Provides read and payment operations for bookings.
Note: Booking creation and cancellation are handled by Reservation Service.
"""

from abc import ABC, abstractmethod
from typing import List

from uuid_utils import UUID

from src.service.ticketing.domain.entity.booking_entity import Booking
from src.service.ticketing.domain.value_object.ticket_ref import TicketRef


class IBookingCommandRepo(ABC):
    """
    Repository interface for booking operations in Ticketing Service.

    Responsibilities:
    - Read booking for validation
    - Payment completion (PENDING_PAYMENT → COMPLETED)

    Note: Booking creation and cancellation are handled by Reservation Service.
    """

    @abstractmethod
    async def get_by_id(self, *, booking_id: UUID) -> Booking | None:
        """
        Get single booking by ID (for validation before command operations)

        Args:
            booking_id: Booking ID

        Returns:
            Booking entity or None if not found
        """
        pass

    @abstractmethod
    async def get_tickets_by_booking_id(self, *, booking_id: UUID) -> List[TicketRef]:
        """
        Get tickets associated with booking (for command operations)

        Args:
            booking_id: Booking ID

        Returns:
            List of ticket references
        """
        pass

    @abstractmethod
    async def complete_booking_and_mark_tickets_sold_atomically(
        self, *, booking: Booking, ticket_ids: list[int]
    ) -> Booking:
        """
        Atomically update booking to COMPLETED and mark tickets as SOLD in single transaction

        Args:
            booking: Booking entity with COMPLETED status
            ticket_ids: List of ticket IDs to mark as SOLD

        Returns:
            Updated booking entity
        """
        pass
