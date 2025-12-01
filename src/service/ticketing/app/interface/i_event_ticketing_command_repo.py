"""
Event Ticketing Command Repository Interface

Unified event ticketing command repository interface - CQRS Write Side
Replaces the previously separated event_command_repo and ticket_command_repo

[Design Principles]
- Operate on Event Aggregate as the unit
- Ensure aggregate transaction consistency
- Only responsible for write operations
- Support batch operation optimization
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import (
    EventTicketingAggregate,
    Ticket,
)
from src.service.ticketing.domain.enum.ticket_status import TicketStatus


class IEventTicketingCommandRepo(ABC):
    """Event Ticketing Command Repository Interface - CQRS Write Side"""

    @abstractmethod
    async def create_event_aggregate(
        self, *, event_aggregate: EventTicketingAggregate
    ) -> EventTicketingAggregate:
        """
        Create Event Aggregate (including Event and Tickets)

        Args:
            event_aggregate: Event aggregate root

        Returns:
            Saved aggregate root (including generated ID)
        """
        pass

    @abstractmethod
    async def create_event_aggregate_with_batch_tickets(
        self,
        *,
        event_aggregate: EventTicketingAggregate,
        ticket_tuples: List[tuple],
    ) -> EventTicketingAggregate:
        """
        Create Event Aggregate with large number of tickets using high-performance batch method

        Note: This method assumes Event already exists and has an ID
        Specifically designed for scenarios requiring creation of large numbers of tickets (e.g., tens of thousands)

        Args:
            event_aggregate: Event aggregate root with existing Event ID
            ticket_tuples: Pre-prepared batch insert data format (optional)

        Returns:
            Saved aggregate root (including all ticket IDs)
        """
        pass

    @abstractmethod
    async def update_event_aggregate(
        self, *, event_aggregate: EventTicketingAggregate
    ) -> EventTicketingAggregate:
        """
        Update Event Aggregate

        Args:
            event_aggregate: Event aggregate root to update

        Returns:
            Updated aggregate root
        """
        pass

    @abstractmethod
    async def update_tickets_status(
        self, *, ticket_ids: List[int], status: TicketStatus, buyer_id: Optional[int] = None
    ) -> List[Ticket]:
        """
        Batch update tickets status

        Args:
            ticket_ids: List of ticket IDs
            status: New status
            buyer_id: Buyer ID (optional)

        Returns:
            List of updated tickets
        """
        pass

    @abstractmethod
    async def delete_event_aggregate(self, *, event_id: int) -> bool:
        """
        Delete Event Aggregate (cascade delete tickets)

        Args:
            event_id: Event ID

        Returns:
            Whether deletion was successful
        """
        pass
