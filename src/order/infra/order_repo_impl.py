"""Order repository implementation."""

from datetime import datetime
from typing import List

from sqlalchemy import select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.order.domain.order_entity import Order, OrderStatus
from src.order.domain.order_repo import OrderRepo
from src.order.infra.order_model import OrderModel
from src.shared.exception.exceptions import DomainError, ForbiddenError, NotFoundError
from src.shared.logging.loguru_io import Logger


class OrderRepoImpl(OrderRepo):
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_entity(db_order: OrderModel) -> Order:
        return Order(
            buyer_id=db_order.buyer_id,
            seller_id=db_order.seller_id,
            event_id=db_order.event_id,
            price=db_order.price,
            status=OrderStatus(db_order.status),
            created_at=db_order.created_at,
            updated_at=db_order.updated_at,
            paid_at=db_order.paid_at,
            id=db_order.id,
        )

    @staticmethod
    def _to_order_dict(db_order: OrderModel) -> dict:
        return {
            'id': db_order.id,
            'buyer_id': db_order.buyer_id,
            'seller_id': db_order.seller_id,
            'event_id': db_order.event_id,
            'price': db_order.price,
            'status': db_order.status,
            'created_at': db_order.created_at,
            'paid_at': db_order.paid_at,
            'event_name': db_order.event.name if db_order.event else 'Unknown Event',
            'buyer_name': db_order.buyer.name if db_order.buyer else 'Unknown Buyer',
            'seller_name': db_order.seller.name if db_order.seller else 'Unknown Seller',
        }

    @Logger.io
    async def create(self, order: Order) -> Order:
        db_order = OrderModel(
            buyer_id=order.buyer_id,
            seller_id=order.seller_id,
            event_id=order.event_id,
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
    async def get_by_id(self, order_id: int) -> Order | None:
        result = await self.session.execute(select(OrderModel).where(OrderModel.id == order_id))
        db_order = result.scalar_one_or_none()

        if not db_order:
            return None

        return OrderRepoImpl._to_entity(db_order)

    @Logger.io
    async def get_by_event_id(self, event_id: int) -> Order | None:
        result = await self.session.execute(
            select(OrderModel)
            .where(OrderModel.event_id == event_id)
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

        return [OrderRepoImpl._to_entity(db_order) for db_order in db_orders]

    @Logger.io
    async def get_by_seller(self, seller_id: int) -> List[Order]:
        result = await self.session.execute(
            select(OrderModel).where(OrderModel.seller_id == seller_id).order_by(OrderModel.id)
        )
        db_orders = result.scalars().all()

        return [OrderRepoImpl._to_entity(db_order) for db_order in db_orders]

    @Logger.io
    async def update(self, order: Order) -> Order:
        stmt = (
            sql_update(OrderModel)
            .where(OrderModel.id == order.id)
            .values(
                buyer_id=order.buyer_id,
                seller_id=order.seller_id,
                event_id=order.event_id,
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
            check_stmt = select(OrderModel).where(OrderModel.id == order_id)
            check_result = await self.session.execute(check_stmt)
            existing_order = check_result.scalar_one_or_none()

            if not existing_order:
                raise NotFoundError('Order not found')
            elif existing_order.buyer_id != buyer_id:
                raise ForbiddenError('Only the buyer can cancel this order')
            elif existing_order.status == OrderStatus.PAID.value:
                raise DomainError('Cannot cancel paid order')
            elif existing_order.status == OrderStatus.CANCELLED.value:
                raise DomainError('Order already cancelled')
            else:
                raise DomainError('Unable to cancel order')

        return OrderRepoImpl._to_entity(db_order)

    @Logger.io
    async def get_buyer_orders_with_details(self, buyer_id: int, status: str) -> List[dict]:
        query = (
            select(OrderModel)
            .options(
                selectinload(OrderModel.event),
                selectinload(OrderModel.buyer),
                selectinload(OrderModel.seller),
            )
            .where(OrderModel.buyer_id == buyer_id)
        )

        if status:
            query = query.where(OrderModel.status == status)

        result = await self.session.execute(query.order_by(OrderModel.id))
        db_orders = result.scalars().all()

        return [OrderRepoImpl._to_order_dict(db_order) for db_order in db_orders]

    @Logger.io
    async def get_seller_orders_with_details(self, seller_id: int, status: str) -> List[dict]:
        query = (
            select(OrderModel)
            .options(
                selectinload(OrderModel.event),
                selectinload(OrderModel.buyer),
                selectinload(OrderModel.seller),
            )
            .where(OrderModel.seller_id == seller_id)
        )

        if status:
            query = query.where(OrderModel.status == status)

        result = await self.session.execute(query.order_by(OrderModel.id))
        db_orders = result.scalars().all()

        return [OrderRepoImpl._to_order_dict(db_order) for db_order in db_orders]
