"""Payment use case for order management."""

import random
import string
from typing import Any, Dict

from fastapi import Depends

from src.order.domain.order_entity import OrderStatus
from src.product.domain.product_entity import ProductStatus
from src.shared.exceptions import BadRequestException, ForbiddenException, NotFoundException
from src.shared.logging.loguru_io import Logger
from src.shared.unit_of_work import AbstractUnitOfWork, get_unit_of_work


class MockPaymentUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow=uow)

    @Logger.io
    async def pay_order(self, order_id: int, buyer_id: int, card_number: str) -> Dict[str, Any]:
        """Process payment for an order."""
        async with self.uow:
            order = await self.uow.orders.get_by_id(order_id)
            if not order:
                raise NotFoundException('Order not found')
            if order.buyer_id != buyer_id:
                raise ForbiddenException('Only the buyer can pay for this order')
            if order.status == OrderStatus.PAID:
                raise BadRequestException('Order already paid')
            elif order.status == OrderStatus.CANCELLED:
                raise BadRequestException('Cannot pay for cancelled order')
            elif order.status != OrderStatus.PENDING_PAYMENT:
                raise BadRequestException('Order is not in a payable state')

            paid_order = order.mark_as_paid()
            updated_order = await self.uow.orders.update(paid_order)
            product = await self.uow.products.get_by_id(order.product_id)
            if product:
                product.status = ProductStatus.SOLD
                await self.uow.products.update(product)
            payment_id = (
                f'PAY_MOCK_{"".join(random.choices(string.ascii_uppercase + string.digits, k=8))}'
            )
            await self.uow.commit()

            return {
                'order_id': updated_order.id,
                'payment_id': payment_id,
                'status': 'paid',
                'paid_at': updated_order.paid_at.isoformat() if updated_order.paid_at else None,
            }

    @Logger.io
    async def cancel_order(self, order_id: int, buyer_id: int) -> None:
        async with self.uow:
            cancelled_order = await self.uow.orders.cancel_order_atomically(order_id, buyer_id)

            await self.uow.products.release_product_atomically(cancelled_order.product_id)

            await self.uow.commit()
