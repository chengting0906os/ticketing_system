"""
Booking Event Publisher Interface

Application layer abstraction for publishing booking domain events.
Follows Dependency Inversion Principle - Use Cases depend on this interface,
not on concrete Kafka/MQ implementations.
"""

from abc import ABC, abstractmethod

from src.service.ticketing.domain.domain_event.booking_domain_event import (
    BookingCancelledEvent,
    BookingCreatedDomainEvent,
    BookingPaidEvent,
)


class IBookingEventPublisher(ABC):
    """
    Port (interface) for publishing booking domain events.

    Responsibilities:
    - Publish booking-related domain events to message queue
    - Handle topic routing internally (infrastructure concern)
    - Ensure event delivery with proper partitioning

    Implementation (Adapter) should handle:
    - Kafka topic name construction
    - Serialization
    - Retry logic
    - Partitioning strategy
    """

    @abstractmethod
    async def publish_booking_created(self, *, event: BookingCreatedDomainEvent) -> None:
        """
        Publish BookingCreated event to trigger seat reservation.

        Args:
            event: BookingCreatedDomainEvent domain event

        Raises:
            EventPublishError: If publishing fails
        """
        pass

    @abstractmethod
    async def publish_booking_paid(self, *, event: BookingPaidEvent) -> None:
        """
        Publish BookingPaidEvent to update ticket status.

        Args:
            event: BookingPaidEvent domain event

        Raises:
            EventPublishError: If publishing fails
        """
        pass

    @abstractmethod
    async def publish_booking_cancelled(self, *, event: BookingCancelledEvent) -> None:
        """
        Publish BookingCancelledEvent to release seats and refund tickets.

        Args:
            event: BookingCancelledEvent domain event

        Raises:
            EventPublishError: If publishing fails
        """
        pass
