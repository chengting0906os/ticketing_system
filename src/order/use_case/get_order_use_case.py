"""Get order use case."""

from fastapi import Depends

from src.order.domain.order_entity import Order
from src.shared.exceptions import NotFoundError
from src.shared.logging.loguru_io import Logger
from src.shared.unit_of_work import AbstractUnitOfWork, get_unit_of_work


class GetOrderUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow=uow)

    @Logger.io
    async def get_order(self, order_id: int) -> Order:
        async with self.uow:
            order = await self.uow.orders.get_by_id(order_id)

            if not order:
                raise NotFoundError('Order not found')

            return order
