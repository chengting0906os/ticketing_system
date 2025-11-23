"""
Event Ticketing Query Repository Interface

Unified event ticketing query repository interface - CQRS Read Side
Replaces the previously separated event_query_repo and ticket_query_repo

[Design Principles]
- Provide rich query interfaces
- Support multiple query perspectives
- Performance optimized query methods
- Only responsible for read operations
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import (
    EventTicketingAggregate,
    Ticket,
)


class IEventTicketingQueryRepo(ABC):
    """Event Ticketing Query Repository Interface - CQRS Read Side"""

    @abstractmethod
    async def get_event_aggregate_by_id_with_tickets(
        self, *, event_id: int
    ) -> Optional[EventTicketingAggregate]:
        """
        Get complete Event Aggregate by ID

        Args:
            event_id: Event ID

        Returns:
            Event aggregate root (including all tickets) or None
        """
        pass

    @abstractmethod
    async def list_events_by_seller(self, *, seller_id: int) -> List[EventTicketingAggregate]:
        """
        Get all events for a seller (excluding tickets for performance optimization)

        Args:
            seller_id: Seller ID

        Returns:
            List of event aggregate roots (tickets as empty list)
        """
        pass

    @abstractmethod
    async def list_available_events(self) -> List[EventTicketingAggregate]:
        """
        Get all available events (excluding tickets for performance optimization)

        Returns:
            List of available event aggregate roots (tickets as empty list)
        """
        pass

    @abstractmethod
    async def get_tickets_by_event_and_section(
        self, *, event_id: int, section: str, subsection: int
    ) -> List[Ticket]:
        """
        Get tickets for a specific section

        Args:
            event_id: Event ID
            section: Section
            subsection: Subsection

        Returns:
            List of tickets
        """
        pass

    @abstractmethod
    async def get_available_tickets_by_event(self, *, event_id: int) -> List[Ticket]:
        """
        Get all available tickets for an event

        Args:
            event_id: Event ID

        Returns:
            List of available tickets
        """
        pass

    @abstractmethod
    async def get_reserved_tickets_by_event(self, *, event_id: int) -> List[Ticket]:
        """
        Get all reserved tickets for an event

        Args:
            event_id: Event ID

        Returns:
            List of reserved tickets
        """
        pass

    @abstractmethod
    async def get_all_tickets_by_event(self, *, event_id: int) -> List[Ticket]:
        """
        Get all tickets for an event (regardless of status)

        Args:
            event_id: Event ID

        Returns:
            List of all tickets
        """
        pass

    @abstractmethod
    async def get_tickets_by_buyer(self, *, buyer_id: int) -> List[Ticket]:
        """
        Get all tickets for a buyer

        Args:
            buyer_id: Buyer ID

        Returns:
            List of tickets
        """
        pass

    @abstractmethod
    async def get_tickets_by_ids(self, *, ticket_ids: List[int]) -> List[Ticket]:
        """
        Get tickets by ID list

        Args:
            ticket_ids: List of ticket IDs

        Returns:
            List of tickets
        """
        pass

    @abstractmethod
    async def check_tickets_exist_for_event(self, *, event_id: int) -> bool:
        """
        Check if tickets exist for an event

        Args:
            event_id: Event ID

        Returns:
            Whether tickets exist
        """
        pass
