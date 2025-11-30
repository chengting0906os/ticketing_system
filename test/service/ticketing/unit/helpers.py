from unittest.mock import AsyncMock, Mock

from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import Ticket
from src.service.ticketing.domain.entity.booking_entity import Booking


class RepositoryMocks:
    def __init__(
        self,
        *,
        booking: Booking | None = None,
        tickets: list[Ticket] | None = None,
        ticket_ids: list[int] | None = None,
    ) -> None:
        """
        Initialize mock repositories with test data

        Args:
            booking: Booking to return from get_by_id
            tickets: Tickets to return from get_tickets_by_ids
            ticket_ids: Ticket IDs to return from seat identifier conversion
        """
        self.booking = booking
        self.tickets = tickets or []
        self.ticket_ids = ticket_ids or []

        # Booking command repo
        self.booking_command_repo: Mock = AsyncMock()
        self.booking_command_repo.get_by_id = AsyncMock(return_value=booking)
        self.booking_command_repo.get_tickets_by_booking_id = AsyncMock(return_value=tickets)

        # Event ticketing command repo
        self.event_ticketing_command_repo: Mock = AsyncMock()
        self.event_ticketing_command_repo.get_ticket_ids_by_seat_identifiers = AsyncMock(
            return_value=ticket_ids
        )
        self.event_ticketing_command_repo.get_tickets_by_ids = AsyncMock(return_value=tickets)
        self.event_ticketing_command_repo.update_tickets_status = AsyncMock()

        # Event ticketing query repo
        self.event_ticketing_query_repo: Mock = AsyncMock()
        self.event_ticketing_query_repo.get_tickets_by_ids = AsyncMock(return_value=tickets)

    async def _update_booking(self, *, booking: Booking) -> Booking:
        """Mock: Return booking as-is (simulates successful persistence)"""
        return booking
