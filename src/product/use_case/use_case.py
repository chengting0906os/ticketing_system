"""Create product use case."""

from uuid import UUID

from fastapi import Depends

from src.product.domain.product_entity import Product
from src.shared.unit_of_work import AbstractUnitOfWork, get_unit_of_work


class CreateProductUseCase:
    
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow
    
    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow)
    
    async def create(
        self, 
        name: str, 
        description: str, 
        price: int, 
        seller_id: UUID
    ) -> Product:
        async with self.uow:
            product = Product.create(
                name=name,
                description=description,
                price=price,
                seller_id=seller_id
            )
            
            created_product = await self.uow.products.create(product)
            await self.uow.commit()
            
        return created_product
