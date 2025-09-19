from typing import Any, Dict

from fastapi import Depends

from src.shared.exception.exceptions import ConflictError, DomainError, NotFoundError
from src.shared.logging.loguru_io import Logger
from src.shared.service.unit_of_work import AbstractUnitOfWork, get_unit_of_work


class ReserveTicketsUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow=uow)

    @Logger.io
    async def reserve_tickets(
        self, *, event_id: int, ticket_count: int, buyer_id: int
    ) -> Dict[str, Any]:
        async with self.uow:
            # Validate ticket count limit
            MAX_TICKETS_PER_RESERVATION = 4
            if ticket_count > MAX_TICKETS_PER_RESERVATION:
                raise DomainError(f'Maximum {MAX_TICKETS_PER_RESERVATION} tickets per person')

            # Get event
            event = await self.uow.events.get_by_id(event_id=event_id)
            if not event:
                raise NotFoundError('Event not found')

            # Get available tickets
            available_tickets = await self.uow.tickets.get_available_tickets_for_event(
                event_id=event_id, limit=ticket_count
            )

            # Check for existing reservations that would conflict
            reserved_tickets = await self.uow.tickets.get_reserved_tickets_for_event(
                event_id=event_id
            )
            if len(reserved_tickets) > 0:
                raise ConflictError('Some tickets are already reserved')

            if len(available_tickets) < ticket_count:
                raise DomainError('Not enough available tickets')

            # Reserve the tickets
            tickets_to_reserve = available_tickets[:ticket_count]
            for ticket in tickets_to_reserve:
                ticket.reserve(buyer_id=buyer_id)

            # Update tickets in database
            await self.uow.tickets.update_batch(tickets=tickets_to_reserve)
            await self.uow.commit()

            # Broadcast WebSocket event (MVP: simple notification)
            from src.shared.websocket.ticket_websocket_service import ticket_websocket_service

            for ticket in tickets_to_reserve:
                ticket_data = {
                    'id': ticket.id,
                    'seat_identifier': ticket.seat_identifier,
                    'price': ticket.price,
                    'status': 'reserved',
                }
                await ticket_websocket_service.broadcast_ticket_event(
                    event_id=event_id, ticket_data=ticket_data, event_type='reserved'
                )

            # Return reservation details
            return {
                'reservation_id': tickets_to_reserve[0].id,  # Use first ticket ID as reservation ID
                'buyer_id': buyer_id,
                'ticket_count': ticket_count,
                'status': 'reserved',
                'tickets': [
                    {
                        'id': ticket.id,
                        'seat_identifier': ticket.seat_identifier,
                        'price': ticket.price,
                    }
                    for ticket in tickets_to_reserve
                ],
            }
