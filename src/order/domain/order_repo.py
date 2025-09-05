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
