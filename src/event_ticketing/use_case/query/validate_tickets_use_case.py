from typing import Dict, List

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.event_ticketing.domain.ticket_repo import TicketRepo
from src.shared.config.db_setting import get_async_session
from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger
from src.shared.service.repo_di import get_ticket_repo


class ValidateTicketsUseCase:
    def __init__(self, session: AsyncSession, ticket_repo: TicketRepo):
        self.session = session
        self.ticket_repo = ticket_repo

    @classmethod
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        ticket_repo: TicketRepo = Depends(get_ticket_repo),
    ):
        return cls(session=session, ticket_repo=ticket_repo)

    @Logger.io
    async def validate_tickets_for_booking(
        self,
        *,
        ticket_ids: List[int],
        seat_locations: Dict[int, str],  # {ticket_id: seat_location}
    ) -> bool:
        """
        Validate that tickets exist and are available for booking.
        Returns True if all tickets are valid, raises DomainError otherwise.
        """
        for ticket_id in ticket_ids:
            ticket = await self.ticket_repo.get_by_id(ticket_id=ticket_id)

            if not ticket:
                raise DomainError(f'Ticket {ticket_id} not found', 404)

            if ticket.status.value != 'available':
                seat_location = seat_locations.get(ticket_id, f'ticket_{ticket_id}')
                raise DomainError(f'Seat {seat_location} is not available', 400)

            if ticket.buyer_id is not None:
                seat_location = seat_locations.get(ticket_id, f'ticket_{ticket_id}')
                raise DomainError(f'Seat {seat_location} is already reserved', 400)

            # Validate seat location matches if provided
            if ticket_id in seat_locations:
                expected_location = (
                    f'{ticket.section}-{ticket.subsection}-{ticket.row}-{ticket.seat}'
                )
                if expected_location != seat_locations[ticket_id]:
                    raise DomainError(f'Seat location mismatch for ticket {ticket_id}', 400)

        return True

    @Logger.io
    async def reserve_tickets(self, *, ticket_ids: List[int], buyer_id: int) -> None:
        # 不使用 async with self.session，因為 session 已經由調用者管理
        tickets = []
        event_ids = set()

        for ticket_id in ticket_ids:
            ticket = await self.ticket_repo.get_by_id(ticket_id=ticket_id)
            if ticket:
                ticket.reserve(buyer_id=buyer_id)
                tickets.append(ticket)
                event_ids.add(ticket.event_id)

        if tickets:
            await self.ticket_repo.update_batch(tickets=tickets)

            # Notify SSE listeners about ticket status changes for each affected event
            for event_id in event_ids:
                await self.session.execute(
                    text(f"NOTIFY ticket_status_change_{event_id}, 'tickets_reserved'")
                )

            await self.session.commit()
