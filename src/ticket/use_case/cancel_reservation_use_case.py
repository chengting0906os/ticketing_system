from typing import Any, Dict

from fastapi import Depends

from src.shared.exception.exceptions import NotFoundError
from src.shared.logging.loguru_io import Logger
from src.shared.service.unit_of_work import AbstractUnitOfWork, get_unit_of_work
from src.ticket.domain.ticket_entity import TicketStatus


class CancelReservationUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow=uow)

    @Logger.io
    async def cancel_reservation(self, *, reservation_id: int, buyer_id: int) -> Dict[str, Any]:
        async with self.uow:
            # Find tickets by reservation_id (using ticket ID as reservation ID for simplicity)
            tickets = await self.uow.tickets.get_reserved_tickets_by_buyer(buyer_id=buyer_id)

            if not tickets:
                raise NotFoundError('Reservation not found')

            # For this implementation, we'll cancel all reserved tickets for the buyer
            # In a more complex system, we'd have a separate reservation table
            reservation_tickets = [t for t in tickets if t.status == TicketStatus.RESERVED]

            if not reservation_tickets:
                raise NotFoundError('No active reservation found')

            # Cancel all reservation tickets
            for ticket in reservation_tickets:
                ticket.cancel_reservation(buyer_id=buyer_id)

            # Update tickets in database
            await self.uow.tickets.update_batch(tickets=reservation_tickets)
            await self.uow.commit()

            return {
                'reservation_id': reservation_id,
                'status': 'cancelled',
                'cancelled_tickets': len(reservation_tickets),
            }
