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
    async def list_by_event_section_and_subsection(
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
    async def get_available_tickets_for_section(
        self, *, event_id: int, section: str, subsection: int, limit: int | None = None
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

    # get_tickets_by_booking_id method moved to BookingRepo
    # since booking now stores ticket_ids instead of tickets storing booking_id

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

    @abstractmethod
    async def get_ticket_stats_by_event(self, *, event_id: int) -> dict:
        """
        Returns ticket statistics for an event.
        Format: {
            'total': int,
            'available': int,
            'reserved': int,
            'sold': int
        }
        """
        pass

    @abstractmethod
    async def get_ticket_stats_by_section(
        self, *, event_id: int, section: str, subsection: int | None = None
    ) -> dict:
        """
        Returns ticket statistics for a section/subsection.
        Format: {
            'total': int,
            'available': int,
            'reserved': int,
            'sold': int
        }
        """
        pass

    @abstractmethod
    async def get_sections_with_stats(self, *, event_id: int) -> List[dict]:
        """
        Returns all sections with their subsection statistics.
        Format: [
            {
                'section': str,
                'subsections': [
                    {
                        'subsection': int,
                        'total': int,
                        'available': int,
                        'reserved': int,
                        'sold': int
                    }
                ]
            }
        ]
        """
        pass
