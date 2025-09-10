"""Order repository interface."""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.order.domain.order_entity import Order


class OrderRepo(ABC):
    @abstractmethod
    async def create(self, order: Order) -> Order:
        pass

    @abstractmethod
    async def get_by_id(self, order_id: int) -> Optional[Order]:
        pass

    @abstractmethod
    async def get_by_product_id(self, product_id: int) -> Optional[Order]:
        pass

    @abstractmethod
    async def get_by_buyer(self, buyer_id: int) -> List[Order]:
        pass

    @abstractmethod
    async def get_by_seller(self, seller_id: int) -> List[Order]:
        pass

    @abstractmethod
    async def update(self, order: Order) -> Order:
        pass

    @abstractmethod
    async def cancel_order_atomically(self, order_id: int, buyer_id: int) -> Order:
        pass

    @abstractmethod
    async def get_buyer_orders_with_details(self, buyer_id: int) -> List[dict]:
        pass

    @abstractmethod
    async def get_seller_orders_with_details(self, seller_id: int) -> List[dict]:
        pass
