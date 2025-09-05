"""Product use cases."""

from typing import Optional

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
        seller_id: int,
        is_active: bool = True
    ) -> Product:
        async with self.uow:
            product = Product.create(
                name=name,
                description=description,
                price=price,
                seller_id=seller_id,
                is_active=is_active,
            )

            created_product = await self.uow.products.create(product)
            await self.uow.commit()
            
        return created_product


class UpdateProductUseCase:
    
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow
    
    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow)
    
    async def update(
        self, 
        product_id: int,
        name: Optional[str] = None, 
        description: Optional[str] = None, 
        price: Optional[int] = None, 
        is_active: Optional[bool] = None
    ) -> Optional[Product]:
        async with self.uow:
            # Get existing product
            product = await self.uow.products.get_by_id(product_id)
            if not product:
                return None
            
            # Update only provided fields
            if name is not None:
                product.name = name
            if description is not None:
                product.description = description
            if price is not None:
                product.price = price
            if is_active is not None:
                product.is_active = is_active
            
            updated_product = await self.uow.products.update(product)
            await self.uow.commit()
            
        return updated_product
