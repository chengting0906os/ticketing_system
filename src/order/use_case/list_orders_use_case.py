"""List orders use case."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import Depends

from src.shared.unit_of_work import AbstractUnitOfWork, get_unit_of_work


class OrderDetailResponse:
    def __init__(
        self,
        id: int,
        buyer_id: int,
        seller_id: int,
        product_id: int,
        price: int,
        status: str,
        created_at: datetime,
        paid_at: Optional[datetime],
        product_name: str,
        buyer_name: str,
        seller_name: str,
    ):
        self.id = id
        self.buyer_id = buyer_id
        self.seller_id = seller_id
        self.product_id = product_id
        self.price = price
        self.status = status
        self.created_at = created_at
        self.paid_at = paid_at
        self.product_name = product_name
        self.buyer_name = buyer_name
        self.seller_name = seller_name

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'buyer_id': self.buyer_id,
            'seller_id': self.seller_id,
            'product_id': self.product_id,
            'price': self.price,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'paid_at': self.paid_at.isoformat() if self.paid_at else None,
            'product_name': self.product_name,
            'buyer_name': self.buyer_name,
            'seller_name': self.seller_name,
        }


class ListOrdersUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow=uow)

    async def list_buyer_orders(
        self, buyer_id: int, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        async with self.uow:
            orders = await self.uow.orders.get_by_buyer(buyer_id)
            if status:
                orders = [o for o in orders if o.status.value == status]
            enriched_orders = []
            for order in orders:
                product = await self.uow.products.get_by_id(order.product_id)
                seller = await self.uow.users.get_by_id(order.seller_id)
                if order.id is None:
                    continue
                order_detail = OrderDetailResponse(
                    id=order.id,
                    buyer_id=order.buyer_id,
                    seller_id=order.seller_id,
                    product_id=order.product_id,
                    price=order.price,
                    status=order.status.value,
                    created_at=order.created_at,
                    paid_at=order.paid_at,
                    product_name=product.name if product else 'Unknown Product',
                    buyer_name='',  # Not needed for buyer's view
                    seller_name=seller.name if seller else 'Unknown Seller',
                )
                enriched_orders.append(order_detail.to_dict())

            return enriched_orders

    async def list_seller_orders(
        self, seller_id: int, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        async with self.uow:
            orders = await self.uow.orders.get_by_seller(seller_id)
            if status:
                orders = [o for o in orders if o.status.value == status]

            enriched_orders = []
            for order in orders:
                product = await self.uow.products.get_by_id(order.product_id)
                buyer = await self.uow.users.get_by_id(order.buyer_id)
                if order.id is None:
                    continue
                order_detail = OrderDetailResponse(
                    id=order.id,
                    buyer_id=order.buyer_id,
                    seller_id=order.seller_id,
                    product_id=order.product_id,
                    price=order.price,
                    status=order.status.value,
                    created_at=order.created_at,
                    paid_at=order.paid_at,
                    product_name=product.name if product else 'Unknown Product',
                    buyer_name=buyer.name if buyer else 'Unknown Buyer',
                    seller_name='',  # Not needed for seller's view
                )
                enriched_orders.append(order_detail.to_dict())

            return enriched_orders
