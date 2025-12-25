"""
Event Ticketing Query Repository Interface

Unified event ticketing query repository interface - CQRS Read Side
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import (
    EventTicketingAggregate,
    SubsectionTicketsAggregate,
)
from src.service.ticketing.domain.entity.ticket_entity import TicketEntity


class IEventTicketingQueryRepo(ABC):
    """Event Ticketing Query Repository Interface - CQRS Read Side"""

    @abstractmethod
    async def get_event_aggregate_by_id_with_tickets(
        self, *, event_id: int
    ) -> Optional[EventTicketingAggregate]:
        """Get complete Event Aggregate by ID."""
        pass

    @abstractmethod
    async def list_events_by_seller(self, *, seller_id: int) -> List[EventTicketingAggregate]:
        """Get all events for a seller (excluding tickets for performance)."""
        pass

    @abstractmethod
    async def list_available_events(self) -> List[EventTicketingAggregate]:
        """Get all available events (excluding tickets for performance)."""
        pass

    @abstractmethod
    async def get_tickets_by_subsection(
        self, *, event_id: int, section: str, subsection: int
    ) -> List[TicketEntity]:
        """Get all tickets for a specific subsection."""
        pass

    @abstractmethod
    async def get_subsection_stats_and_tickets(
        self, *, event_id: int, section: str, subsection: int
    ) -> Optional[SubsectionTicketsAggregate]:
        """Get subsection stats with tickets."""
        pass
