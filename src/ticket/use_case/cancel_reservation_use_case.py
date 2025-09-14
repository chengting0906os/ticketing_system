from typing import Any, Dict

from fastapi import Depends

from src.shared.exception.exceptions import NotFoundError
from src.shared.logging.loguru_io import Logger
from src.shared.service.unit_of_work import AbstractUnitOfWork, get_unit_of_work


class CancelReservationUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow=uow)

    @Logger.io
    async def cancel_reservation(self, *, order_id: int, buyer_id: int) -> Dict[str, Any]:
        async with self.uow:
            # Get the order first to verify ownership and status
            order = await self.uow.orders.get_by_id(order_id=order_id)
            if not order:
                raise NotFoundError('Order not found')

            # Verify order belongs to requesting buyer
            if order.buyer_id != buyer_id:
                from src.shared.exception.exceptions import ForbiddenError

                raise ForbiddenError('Only the buyer can cancel this order')

            # Check if order can be cancelled
            from src.order.domain.order_entity import OrderStatus

            if order.status == OrderStatus.PAID:
                from src.shared.exception.exceptions import DomainError

                raise DomainError('Cannot cancel paid order', 400)
            elif order.status == OrderStatus.CANCELLED:
                from src.shared.exception.exceptions import DomainError

                raise DomainError('Order already cancelled', 400)

            # Find tickets by order_id
            tickets = await self.uow.tickets.get_tickets_by_order_id(order_id=order_id)

            if not tickets:
                raise NotFoundError('Order not found')

            # Cancel all tickets associated with this order (release them back to available)
            for ticket in tickets:
                ticket.cancel_reservation(buyer_id=buyer_id)

            # Update order status to cancelled
            cancelled_order = order.cancel()
            await self.uow.orders.update(order=cancelled_order)

            # Update tickets in database
            await self.uow.tickets.update_batch(tickets=tickets)
            await self.uow.commit()

            return {
                'status': 'ok',
                'cancelled_tickets': len(tickets),
            }
