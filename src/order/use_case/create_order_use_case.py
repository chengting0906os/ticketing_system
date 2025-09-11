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
        self.email_use_case = MockSendEmailUseCase(email_service)

    @classmethod
    def depends(
        cls,
        uow: AbstractUnitOfWork = Depends(get_unit_of_work),
        email_service: MockEmailService = Depends(get_mock_email_service),
    ):
        return cls(uow, email_service)

    @Logger.io
    async def create_order(self, buyer_id: int, event_id: int) -> Order:
        async with self.uow:
            buyer = await self.uow.users.get_by_id(buyer_id)
            if not buyer:
                raise DomainError('Buyer not found', 404)
            # Get event and seller in one JOIN query
            event, seller = await self.uow.events.get_by_id_with_seller(event_id)
            if not event:
                raise DomainError('Event not found', 404)
            if not seller:
                raise DomainError('Seller not found', 404)

            aggregate = OrderAggregate.create_order(buyer, event, seller)
            created_order = await self.uow.orders.create(aggregate.order)
            aggregate.order.id = created_order.id
            aggregate.emit_creation_events()
            events = aggregate.collect_events()
            for event in events:
                await self.email_use_case.handle_notification(event)

            updated_event = aggregate.get_event_for_update()
            if updated_event:
                await self.uow.events.update(updated_event)

            await self.uow.commit()

        return created_order
