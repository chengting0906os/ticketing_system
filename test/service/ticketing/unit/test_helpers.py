"""
Test helpers for unit tests

Provides reusable test doubles (stubs, mocks, fakes) for common dependencies
"""

from typing import List
from unittest.mock import AsyncMock
from uuid import UUID

from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import Ticket
from src.service.ticketing.domain.entity.booking_entity import Booking


class RepositoryMocks:
    """
    Mock repositories container for testing use cases

    Organizes related mock repositories in one place for easier test setup.
    This is NOT a UoW - just a container for organizing mocks.

    Example:
        ```python
        mocks = RepositoryMocks(
            booking=some_booking,
            tickets=[ticket1, ticket2],
            ticket_ids=[TEST_TICKET_ID_1, TEST_TICKET_ID_2],
        )
        use_case = SomeUseCase(
            booking_command_repo=mocks.booking_command_repo,
            event_ticketing_command_repo=mocks.event_ticketing_command_repo,
        )
        result = await use_case.execute(...)
        ```
    """

    def __init__(
        self,
        *,
        booking: Booking | None = None,
        tickets: List[Ticket] | None = None,
        ticket_ids: List[UUID] | None = None,
    ):
        """
        Initialize mock repositories with test data

        Args:
            booking: Booking to return from get_by_id
            tickets: Tickets to return from get_tickets_by_ids
            ticket_ids: Ticket IDs (UUIDs) to return from seat identifier conversion
        """
        self.booking = booking
        self.tickets = tickets or []
        self.ticket_ids = ticket_ids or []

        # Booking command repo
        self.booking_command_repo = AsyncMock()
        self.booking_command_repo.get_by_id = AsyncMock(return_value=booking)
        self.booking_command_repo.get_tickets_by_booking_id = AsyncMock(return_value=tickets)
        self.booking_command_repo.update_status_to_pending_payment = AsyncMock(
            side_effect=self._update_booking
        )

        # Event ticketing command repo
        self.event_ticketing_command_repo = AsyncMock()
        self.event_ticketing_command_repo.get_ticket_ids_by_seat_identifiers = AsyncMock(
            return_value=ticket_ids
        )
        self.event_ticketing_command_repo.get_tickets_by_ids = AsyncMock(return_value=tickets)
        self.event_ticketing_command_repo.update_tickets_status = AsyncMock()

        # Event ticketing query repo
        self.event_ticketing_query_repo = AsyncMock()
        self.event_ticketing_query_repo.get_tickets_by_ids = AsyncMock(return_value=tickets)

        # SSE broadcaster
        self.sse_broadcaster = AsyncMock()

    async def _update_booking(self, *, booking: Booking) -> Booking:
        """Mock: Return booking as-is (simulates successful persistence)"""
        return booking
