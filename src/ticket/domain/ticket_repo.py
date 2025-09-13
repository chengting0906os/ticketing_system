"""Ticket repository interface."""

from abc import ABC, abstractmethod
from typing import List

from src.ticket.domain.ticket_entity import Ticket


class TicketRepo(ABC):
    @abstractmethod
    async def create_batch(self, tickets: List[Ticket]) -> List[Ticket]:
        """Create multiple tickets in batch."""
        pass

    @abstractmethod
    async def get_by_event_id(self, event_id: int) -> List[Ticket]:
        """Get all tickets for an event."""
        pass

    @abstractmethod
    async def get_by_event_and_section(
        self, event_id: int, section: str, subsection: int | None = None
    ) -> List[Ticket]:
        """Get tickets for specific section/subsection of an event."""
        pass

    @abstractmethod
    async def check_tickets_exist_for_event(self, event_id: int) -> bool:
        """Check if any tickets exist for an event."""
        pass

    @abstractmethod
    async def count_tickets_by_event(self, event_id: int) -> int:
        """Count total tickets for an event."""
        pass

    @abstractmethod
    async def get_available_tickets_by_event(self, event_id: int) -> List[Ticket]:
        """Get all available tickets for an event."""
        pass
