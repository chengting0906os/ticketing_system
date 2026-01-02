"""
Event Ticketing Command Repository Interface

Unified event ticketing command repository interface - CQRS Write Side
"""

from abc import ABC, abstractmethod
from typing import List

from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import (
    EventTicketingAggregate,
)


class IEventTicketingCommandRepo(ABC):
    """Event Ticketing Command Repository Interface - CQRS Write Side"""

    @abstractmethod
    async def create_event_aggregate(
        self, *, event_aggregate: EventTicketingAggregate
    ) -> EventTicketingAggregate:
        """Create Event Aggregate (including Event and Tickets)."""
        pass

    @abstractmethod
    async def create_event_aggregate_with_batch_tickets(
        self,
        *,
        event_aggregate: EventTicketingAggregate,
        ticket_tuples: List[tuple],
    ) -> EventTicketingAggregate:
        """Create Event Aggregate with batch tickets (high-performance)."""
        pass

    @abstractmethod
    async def update_event_status(self, *, event_id: int, status: str) -> None:
        """Update Event status only (without updating tickets)."""
        pass

    @abstractmethod
    async def delete_event_aggregate(self, *, event_id: int) -> bool:
        """Delete Event Aggregate (cascade delete tickets)."""
        pass
