from abc import ABC, abstractmethod
from typing import List

from src.event_ticketing.domain.ticket_entity import Ticket


class TicketCommandRepo(ABC):
    @abstractmethod
    async def create_batch(self, *, tickets: List[Ticket]) -> List[Ticket]:
        pass

    @abstractmethod
    async def update_batch(self, *, tickets: List[Ticket]) -> List[Ticket]:
        pass
