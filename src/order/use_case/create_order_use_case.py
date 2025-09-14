from typing import List
from fastapi import Depends

from src.order.domain.order_aggregate import OrderAggregate
from src.order.domain.order_entity import Order
from src.order.use_case.mock_send_email_use_case import MockSendEmailUseCase
from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger
from src.shared.service.mock_email_service import MockEmailService, get_mock_email_service
from src.shared.service.unit_of_work import AbstractUnitOfWork, get_unit_of_work


class CreateOrderUseCase:
    def __init__(self, uow: AbstractUnitOfWork, email_service: MockEmailService):
        self.uow = uow
        self.email_service = email_service
        self.email_use_case = MockSendEmailUseCase(email_service)

    @classmethod
    def depends(
        cls,
        uow: AbstractUnitOfWork = Depends(get_unit_of_work),
        email_service: MockEmailService = Depends(get_mock_email_service),
    ):
        return cls(uow, email_service)

    @Logger.io
    async def create_order(self, buyer_id: int, ticket_ids: List[int]) -> Order:
        async with self.uow:
            # Validate maximum 4 tickets per order
            if len(ticket_ids) > 4:
                raise DomainError('Maximum 4 tickets per order', 400)
            if len(ticket_ids) == 0:
                raise DomainError('At least 1 ticket required', 400)

            buyer = await self.uow.users.get_by_id(user_id=buyer_id)
            if not buyer:
                raise DomainError('Buyer not found', 404)

            # Get tickets by IDs
            tickets = []
            for ticket_id in ticket_ids:
                ticket = await self.uow.tickets.get_by_id(ticket_id=ticket_id)
                if ticket:
                    tickets.append(ticket)

            if len(tickets) != len(ticket_ids):
                raise DomainError('Some tickets not found', 404)

            # Validate all tickets are available and can be reserved
            for ticket in tickets:
                if ticket.status.value != 'available':
                    raise DomainError('All tickets must be available', 400)
                if ticket.buyer_id is not None:
                    raise DomainError('Tickets are already reserved', 400)
                if ticket.order_id is not None:
                    raise DomainError('Tickets are already in an order', 400)

            # Get event info from first ticket (all should be same event)
            event_id = tickets[0].event_id
            if not all(ticket.event_id == event_id for ticket in tickets):
                raise DomainError('All tickets must be for the same event', 400)

            event, seller = await self.uow.events.get_by_id_with_seller(event_id=event_id)
            if not event:
                raise DomainError('Event not found', 404)
            if not seller:
                raise DomainError('Seller not found', 404)

            # Validate event is available for ordering
            if not event.is_active:
                raise DomainError('Event not active', 400)
            # Note: Event status (available/sold_out/ended) doesn't prevent ordering
            # Individual ticket availability is checked separately

            # Reserve tickets for this buyer
            for ticket in tickets:
                ticket.reserve(buyer_id=buyer_id)

            # Create order using OrderAggregate
            aggregate = OrderAggregate.create_order(buyer, tickets, seller)
            created_order = await self.uow.orders.create(order=aggregate.order)
            aggregate.order.id = created_order.id

            # Update tickets with order_id and reserved status
            for ticket in tickets:
                ticket.order_id = created_order.id
            await self.uow.tickets.update_batch(tickets=tickets)

            aggregate.emit_creation_events()
            events = aggregate.collect_events()
            for event in events:
                await self.email_use_case.handle_notification(event)

            await self.uow.commit()

        return created_order
