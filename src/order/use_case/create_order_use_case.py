"""Create order use case."""

from fastapi import Depends

from src.order.domain.order_aggregate import OrderAggregate
from src.order.domain.order_entity import Order
from src.order.use_case.mock_send_email_use_case import MockSendEmailUseCase
from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger
from src.shared.service.mock_email_service import MockEmailService, get_mock_email_service
from src.shared.service.unit_of_work import AbstractUnitOfWork, get_unit_of_work


class CreateOrderUseCase:
    def __init__(self, uow: AbstractUnitOfWork, email_service: MockEmailService):
        self.uow = uow
        self.email_service = email_service
        self.email_use_case = MockSendEmailUseCase(email_service, uow)

    @classmethod
    def depends(
        cls,
        uow: AbstractUnitOfWork = Depends(get_unit_of_work),
        email_service: MockEmailService = Depends(get_mock_email_service),
    ):
        return cls(uow, email_service)

    @Logger.io
    async def create_order(self, buyer_id: int, product_id: int) -> Order:
        async with self.uow:
            buyer = await self.uow.users.get_by_id(buyer_id)
            if not buyer:
                raise DomainError('Buyer not found', 404)
            product = await self.uow.products.get_by_id(product_id)
            if not product:
                raise DomainError('Product not found', 404)

            if product.id:
                existing_order = await self.uow.orders.get_by_product_id(product.id)
                if existing_order:
                    raise DomainError('Product already has an active order', 400)

            aggregate = OrderAggregate.create_order(buyer, product)
            created_order = await self.uow.orders.create(aggregate.order)
            aggregate.order.id = created_order.id

            # Recreate events with the correct order ID
            if created_order.id:
                aggregate.recreate_events_with_order_id(created_order.id)

            events = aggregate.collect_events()
            for event in events:
                await self.email_use_case.handle(event)

            updated_product = aggregate.get_product_for_update()
            if updated_product:
                await self.uow.products.update(updated_product)

            await self.uow.commit()

        return created_order
