"""Product repository interface."""

from abc import ABC, abstractmethod
from typing import Optional

from src.product.domain.product_entity import Product


class ProductRepo(ABC):
    
    @abstractmethod
    async def create(self, product: Product) -> Product:
        pass
    
    @abstractmethod
    async def get_by_id(self, product_id: int) -> Optional[Product]:
        pass
    
    @abstractmethod
    async def update(self, product: Product) -> Product:
        pass
    
    @abstractmethod
    async def delete(self, product_id: int) -> bool:
        pass
