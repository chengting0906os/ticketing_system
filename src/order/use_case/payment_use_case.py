"""Payment use case for order management."""

import random
import string
from typing import Any, Dict

from fastapi import Depends

from src.order.domain.order_entity import OrderStatus
from src.product.domain.product_entity import ProductStatus
from src.shared.exceptions import BadRequestException, ForbiddenException, NotFoundException
from src.shared.unit_of_work import AbstractUnitOfWork, get_unit_of_work


class PaymentUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow=uow)

    async def pay_order(self, order_id: int, buyer_id: int, card_number: str) -> Dict[str, Any]:
        """Process payment for an order."""
        async with self.uow:
            # Get the order
            order = await self.uow.orders.get_by_id(order_id)
            if not order:
                raise NotFoundException("Order not found")
            
            # Check if the buyer is the owner of the order
            if order.buyer_id != buyer_id:
                raise ForbiddenException("Only the buyer can pay for this order")
            
            # Check if order is in pending_payment status
            if order.status == OrderStatus.PAID:
                raise BadRequestException("Order already paid")
            elif order.status == OrderStatus.CANCELLED:
                raise BadRequestException("Cannot pay for cancelled order")
            elif order.status != OrderStatus.PENDING_PAYMENT:
                raise BadRequestException("Order is not in a payable state")
            
            # Mark order as paid
            paid_order = order.mark_as_paid()
            updated_order = await self.uow.orders.update(paid_order)
            
            # Update product status to sold
            product = await self.uow.products.get_by_id(order.product_id)
            if product:
                product.status = ProductStatus.SOLD
                await self.uow.products.update(product)
            
            # Generate mock payment ID
            payment_id = f"PAY_MOCK_{''.join(random.choices(string.ascii_uppercase + string.digits, k=8))}"
            
            await self.uow.commit()
            
            return {
                "order_id": updated_order.id,
                "payment_id": payment_id,
                "status": "paid",
                "paid_at": updated_order.paid_at.isoformat() if updated_order.paid_at else None
            }

    async def cancel_order(self, order_id: int, buyer_id: int) -> None:
        """Cancel an order."""
        async with self.uow:
            # Get the order
            order = await self.uow.orders.get_by_id(order_id)
            if not order:
                raise NotFoundException("Order not found")
            
            # Check if the buyer is the owner of the order
            if order.buyer_id != buyer_id:
                raise ForbiddenException("Only the buyer can cancel this order")
            
            # Check if order can be cancelled
            if order.status == OrderStatus.PAID:
                raise BadRequestException("Cannot cancel paid order")
            elif order.status == OrderStatus.CANCELLED:
                raise BadRequestException("Order is already cancelled")
            
            # Cancel the order
            cancelled_order = order.cancel()
            await self.uow.orders.update(cancelled_order)
            
            # Update product status back to available
            product = await self.uow.products.get_by_id(order.product_id)
            if product:
                product.status = ProductStatus.AVAILABLE
                await self.uow.products.update(product)
            
            await self.uow.commit()
