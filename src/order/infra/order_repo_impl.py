"""Order repository implementation."""

from typing import List, Optional

from sqlalchemy import select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.logging.loguru_io import Logger
from src.order.domain.order_entity import Order, OrderStatus
from src.order.domain.order_repo import OrderRepo
from src.order.infra.order_model import OrderModel


class OrderRepoImpl(OrderRepo):
    def __init__(self, session: AsyncSession):
        self.session = session

    @Logger.io
    async def create(self, order: Order) -> Order:
        db_order = OrderModel(
            buyer_id=order.buyer_id,
            seller_id=order.seller_id,
            product_id=order.product_id,
            price=order.price,
            status=order.status.value,
            created_at=order.created_at,
            updated_at=order.updated_at,
            paid_at=order.paid_at,
        )
        self.session.add(db_order)
        await self.session.flush()
        await self.session.refresh(db_order)

        return Order(
            buyer_id=db_order.buyer_id,
            seller_id=db_order.seller_id,
            product_id=db_order.product_id,
            price=db_order.price,
            status=OrderStatus(db_order.status),
            created_at=db_order.created_at,
            updated_at=db_order.updated_at,
            paid_at=db_order.paid_at,
            id=db_order.id,
        )

    @Logger.io
    async def get_by_id(self, order_id: int) -> Optional[Order]:
        result = await self.session.execute(select(OrderModel).where(OrderModel.id == order_id))
        db_order = result.scalar_one_or_none()

        if not db_order:
            return None

        return Order(
            buyer_id=db_order.buyer_id,
            seller_id=db_order.seller_id,
            product_id=db_order.product_id,
            price=db_order.price,
            status=OrderStatus(db_order.status),
            created_at=db_order.created_at,
            updated_at=db_order.updated_at,
            paid_at=db_order.paid_at,
            id=db_order.id,
        )

    @Logger.io
    async def get_by_product_id(self, product_id: int) -> Optional[Order]:
        result = await self.session.execute(
            select(OrderModel)
            .where(OrderModel.product_id == product_id)
            .where(OrderModel.status != OrderStatus.CANCELLED.value)
        )
        db_order = result.scalar_one_or_none()

        if not db_order:
            return None

        return Order(
            buyer_id=db_order.buyer_id,
            seller_id=db_order.seller_id,
            product_id=db_order.product_id,
            price=db_order.price,
            status=OrderStatus(db_order.status),
            created_at=db_order.created_at,
            updated_at=db_order.updated_at,
            paid_at=db_order.paid_at,
            id=db_order.id,
        )

    @Logger.io
    async def get_by_buyer(self, buyer_id: int) -> List[Order]:
        result = await self.session.execute(
            select(OrderModel).where(OrderModel.buyer_id == buyer_id).order_by(OrderModel.id)
        )
        db_orders = result.scalars().all()

        return [
            Order(
                buyer_id=db_order.buyer_id,
                seller_id=db_order.seller_id,
                product_id=db_order.product_id,
                price=db_order.price,
                status=OrderStatus(db_order.status),
                created_at=db_order.created_at,
                updated_at=db_order.updated_at,
                paid_at=db_order.paid_at,
                id=db_order.id,
            )
            for db_order in db_orders
        ]

    @Logger.io
    async def get_by_seller(self, seller_id: int) -> List[Order]:
        result = await self.session.execute(
            select(OrderModel).where(OrderModel.seller_id == seller_id).order_by(OrderModel.id)
        )
        db_orders = result.scalars().all()

        return [
            Order(
                buyer_id=db_order.buyer_id,
                seller_id=db_order.seller_id,
                product_id=db_order.product_id,
                price=db_order.price,
                status=OrderStatus(db_order.status),
                created_at=db_order.created_at,
                updated_at=db_order.updated_at,
                paid_at=db_order.paid_at,
                id=db_order.id,
            )
            for db_order in db_orders
        ]

    @Logger.io
    async def update(self, order: Order) -> Order:
        stmt = (
            sql_update(OrderModel)
            .where(OrderModel.id == order.id)
            .values(
                buyer_id=order.buyer_id,
                seller_id=order.seller_id,
                product_id=order.product_id,
                price=order.price,
                status=order.status.value,
                updated_at=order.updated_at,
                paid_at=order.paid_at,
            )
            .returning(OrderModel)
        )

        result = await self.session.execute(stmt)
        db_order = result.scalar_one_or_none()

        if not db_order:
            raise ValueError(f'Order with id {order.id} not found')

        return Order(
            buyer_id=db_order.buyer_id,
            seller_id=db_order.seller_id,
            product_id=db_order.product_id,
            price=db_order.price,
            status=OrderStatus(db_order.status),
            created_at=db_order.created_at,
            updated_at=db_order.updated_at,
            paid_at=db_order.paid_at,
            id=db_order.id,
        )
