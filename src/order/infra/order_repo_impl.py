"""Order repository implementation."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from src.order.domain.order_entity import Order, OrderStatus
from src.order.domain.order_repo import OrderRepo
from src.order.infra.order_model import OrderModel
from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger


class OrderRepoImpl(OrderRepo):
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_entity(db_order: OrderModel) -> Order:
        """Convert database model to domain entity."""
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

        return OrderRepoImpl._to_entity(db_order)

    @Logger.io
    async def get_by_id(self, order_id: int) -> Optional[Order]:
        result = await self.session.execute(select(OrderModel).where(OrderModel.id == order_id))
        db_order = result.scalar_one_or_none()

        if not db_order:
            return None

        return OrderRepoImpl._to_entity(db_order)

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

        return OrderRepoImpl._to_entity(db_order)

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

        return OrderRepoImpl._to_entity(db_order)

    @Logger.io
    async def cancel_order_atomically(self, order_id: int, buyer_id: int) -> Order:
        stmt = (
            sql_update(OrderModel)
            .where(OrderModel.id == order_id)
            .where(OrderModel.buyer_id == buyer_id)
            .where(OrderModel.status == OrderStatus.PENDING_PAYMENT.value)
            .values(status=OrderStatus.CANCELLED.value, updated_at=datetime.now())
            .returning(OrderModel)
        )

        result = await self.session.execute(stmt)
        db_order = result.scalar_one_or_none()

        if not db_order:
            # Need to check the actual reason for better error messages
            check_stmt = select(OrderModel).where(OrderModel.id == order_id)
            check_result = await self.session.execute(check_stmt)
            existing_order = check_result.scalar_one_or_none()

            if not existing_order:
                raise DomainError('Order not found')
            elif existing_order.status == OrderStatus.PAID.value:
                raise DomainError('Cannot cancel paid order')
            elif existing_order.status == OrderStatus.CANCELLED.value:
                raise DomainError('Order already cancelled')
            else:
                raise DomainError('Unable to cancel order')

        return OrderRepoImpl._to_entity(db_order)
