"""Product repository interface."""

from abc import ABC, abstractmethod

from src.product.domain.product_entity import Product


class ProductRepo(ABC):
    
    @abstractmethod
    async def create(self, product: Product) -> Product:
        pass
