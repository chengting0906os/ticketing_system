from abc import ABC, abstractmethod
from typing import List

from src.event_ticketing.domain.ticket_entity import Ticket


class TicketRepo(ABC):
    @abstractmethod
    async def get_by_id(self, *, ticket_id: int) -> Ticket | None:
        pass

    @abstractmethod
    async def create_batch(self, *, tickets: List[Ticket]) -> List[Ticket]:
        pass

    @abstractmethod
    async def get_by_event_id(self, *, event_id: int) -> List[Ticket]:
        pass

    @abstractmethod
    async def get_by_event_and_section(
        self, *, event_id: int, section: str, subsection: int | None = None
    ) -> List[Ticket]:
        pass

    @abstractmethod
    async def check_tickets_exist_for_event(self, *, event_id: int) -> bool:
        pass

    @abstractmethod
    async def count_tickets_by_event(self, *, event_id: int) -> int:
        pass

    @abstractmethod
    async def get_available_tickets_by_event(self, *, event_id: int) -> List[Ticket]:
        pass

    @abstractmethod
    async def get_available_tickets_for_event(
        self, *, event_id: int, limit: int | None = None
    ) -> List[Ticket]:
        pass

    @abstractmethod
    async def get_reserved_tickets_for_event(self, *, event_id: int) -> List[Ticket]:
        pass

    @abstractmethod
    async def get_reserved_tickets_by_buyer(self, *, buyer_id: int) -> List[Ticket]:
        pass

    @abstractmethod
    async def get_reserved_tickets_by_buyer_and_event(
        self, *, buyer_id: int, event_id: int
    ) -> List[Ticket]:
        pass

    @abstractmethod
    async def get_tickets_by_booking_id(self, *, booking_id: int) -> List[Ticket]:
        pass

    @abstractmethod
    async def get_all_reserved_tickets(self) -> List[Ticket]:
        pass

    @abstractmethod
    async def update_batch(self, *, tickets: List[Ticket]) -> List[Ticket]:
        pass

    @abstractmethod
    async def get_all_available(self) -> List[Ticket]:
        pass

    @abstractmethod
    async def get_by_seat_location(
        self, *, section: str, subsection: int, row_number: int, seat_number: int
    ) -> Ticket | None:
        pass

    @abstractmethod
    async def get_available_tickets_limit(self, *, limit: int) -> List[Ticket]:
        pass
