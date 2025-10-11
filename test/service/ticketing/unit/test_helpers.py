"""
Test helpers for unit tests

Provides reusable test doubles (stubs, mocks, fakes) for common dependencies
"""

from typing import List
from unittest.mock import AsyncMock

from src.platform.database.unit_of_work import AbstractUnitOfWork
from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import Ticket
from src.service.ticketing.domain.entity.booking_entity import Booking


class StubUnitOfWork(AbstractUnitOfWork):
    """
    Reusable UoW stub for testing use cases

    Provides default test behavior that can be customized per test.
    This is a Stub pattern - returns predetermined values without complex logic.

    Example:
        ```python
        stub_uow = StubUnitOfWork(
            booking=some_booking,
            tickets=[ticket1, ticket2],
            ticket_ids=[1, 2],
        )
        use_case = SomeUseCase(uow=stub_uow)
        result = await use_case.execute(...)
        ```
    """

    def __init__(
        self,
        *,
        booking: Booking | None = None,
        tickets: List[Ticket] | None = None,
        ticket_ids: List[int] | None = None,
    ):
        """
        Initialize stub with test data

        Args:
            booking: Booking to return from get_by_id
            tickets: Tickets to return from get_tickets_by_ids
            ticket_ids: Ticket IDs to return from seat identifier conversion
        """
        self.booking = booking
        self.tickets = tickets or []
        self.ticket_ids = ticket_ids or []
        self.committed = False

        # Booking command repo
        self.booking_command_repo = AsyncMock()
        self.booking_command_repo.get_by_id = AsyncMock(return_value=booking)
        self.booking_command_repo.update_status_to_pending_payment = AsyncMock(
            side_effect=self._update_booking
        )
        self.booking_command_repo.link_tickets_to_booking = AsyncMock()

        # Event ticketing command repo
        self.event_ticketing_command_repo = AsyncMock()
        self.event_ticketing_command_repo.get_ticket_ids_by_seat_identifiers = AsyncMock(
            return_value=ticket_ids
        )
        self.event_ticketing_command_repo.update_tickets_status = AsyncMock()

        # Event ticketing query repo
        self.event_ticketing_query_repo = AsyncMock()
        self.event_ticketing_query_repo.get_tickets_by_ids = AsyncMock(return_value=tickets)

    async def _update_booking(self, *, booking: Booking) -> Booking:
        """Stub: Return booking as-is (simulates successful persistence)"""
        return booking

    async def _commit(self):
        """Stub: Mark as committed"""
        self.committed = True

    async def rollback(self):
        """Stub: No-op rollback for tests"""
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass
