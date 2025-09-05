"""Create order use case."""

from fastapi import Depends

from src.order.domain.order_entity import Order
from src.product.domain.product_entity import ProductStatus
from src.shared.exceptions import DomainException
from src.shared.unit_of_work import AbstractUnitOfWork, get_unit_of_work
from src.user.domain.user_entity import UserRole


class CreateOrderUseCase:
    
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow
    
    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow)
    
    async def create_order(self, buyer_id: int, product_id: int) -> Order:
        async with self.uow:
            buyer = await self.uow.users.get_by_id(buyer_id)
            
            if not buyer:
                raise DomainException(status_code=404, message="Buyer not found")
            
            if buyer.role != UserRole.BUYER.value:
                raise DomainException(status_code=403, message="Only buyers can create orders")
            
            product = await self.uow.products.get_by_id(product_id)
            if not product:
                raise DomainException(status_code=404, message="Product not found")
            
            if not product.is_active:
                raise DomainException(status_code=400, message="Product not active")
            
            if product.status != ProductStatus.AVAILABLE:
                raise DomainException(status_code=400, message="Product not available")
            
            if buyer.id == product.seller_id:
                raise DomainException(status_code=403, message="Only buyers can create orders")
            
            if product.id:
                existing_order = await self.uow.orders.get_by_product_id(product.id)
                if existing_order:
                    raise DomainException(status_code=400, message="Product already has an active order")
            
            order = Order.create(
                buyer_id=buyer_id,
                seller_id=product.seller_id,
                product_id=product.id or 0,
                price=product.price
            )
            
            created_order = await self.uow.orders.create(order)
            
            product.status = ProductStatus.RESERVED
            await self.uow.products.update(product)
            
            await self.uow.commit()
            
        return created_order
