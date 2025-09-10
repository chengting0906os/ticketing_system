"""Product repository interface."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional


if TYPE_CHECKING:
    from src.user.domain.user_model import User

from src.product.domain.product_entity import Product


class ProductRepo(ABC):
    @abstractmethod
    async def create(self, product: Product) -> Product:
        pass

    @abstractmethod
    async def get_by_id(self, product_id: int) -> Optional[Product]:
        pass

    @abstractmethod
    async def get_by_id_with_seller(
        self, product_id: int
    ) -> tuple[Optional[Product], Optional['User']]:
        pass

    @abstractmethod
    async def update(self, product: Product) -> Product:
        pass

    @abstractmethod
    async def delete(self, product_id: int) -> bool:
        pass

    @abstractmethod
    async def get_by_seller(self, seller_id: int) -> List[Product]:
        pass

    @abstractmethod
    async def list_available(self) -> List[Product]:
        pass

    @abstractmethod
    async def release_product_atomically(self, product_id: int) -> Product:
        pass
