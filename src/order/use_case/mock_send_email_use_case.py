"""Email notification use case for order domain events."""

from src.shared.logging.loguru_io import Logger
from src.order.domain.events import (
    DomainEventProtocol,
    OrderCancelledEvent,
    OrderCreatedEvent,
    OrderPaidEvent,
)
from src.shared.mock_email_service import MockEmailService
from src.shared.unit_of_work import AbstractUnitOfWork


class MockSendEmailUseCase:
    def __init__(self, email_service: MockEmailService, uow: AbstractUnitOfWork):
        self.email_service = email_service
        self.uow = uow

    @Logger.io
    async def handle_order_created(self, event: OrderCreatedEvent):
        buyer = await self.uow.users.get_by_id(event.buyer_id)
        product = await self.uow.products.get_by_id(event.product_id)
        seller = await self.uow.users.get_by_id(event.seller_id)

        if buyer and product:
            await self.email_service.send_order_confirmation(
                buyer_email=buyer.email,
                order_id=event.aggregate_id,
                product_name=product.name,
                price=event.price,
            )

        if seller and product and buyer:
            await self.email_service.notify_seller_new_order(
                seller_email=seller.email,
                order_id=event.aggregate_id,
                product_name=product.name,
                buyer_name=buyer.name,
                price=event.price,
            )

    @Logger.io
    async def handle_order_paid(self, event: OrderPaidEvent):
        buyer = await self.uow.users.get_by_id(event.buyer_id)
        product = await self.uow.products.get_by_id(event.product_id)

        if buyer and product:
            await self.email_service.send_payment_confirmation(
                buyer_email=buyer.email,
                order_id=event.aggregate_id,
                product_name=product.name,
                paid_amount=product.price,
            )

    @Logger.io
    async def handle_order_cancelled(self, event: OrderCancelledEvent):
        buyer = await self.uow.users.get_by_id(event.buyer_id)
        product = await self.uow.products.get_by_id(event.product_id)

        if buyer and product:
            await self.email_service.send_order_cancellation(
                buyer_email=buyer.email,
                order_id=event.aggregate_id,
                product_name=product.name,
                reason=event.reason,
            )

    @Logger.io
    async def handle(self, event: DomainEventProtocol):
        if isinstance(event, OrderCreatedEvent):
            await self.handle_order_created(event)
        elif isinstance(event, OrderPaidEvent):
            await self.handle_order_paid(event)
        elif isinstance(event, OrderCancelledEvent):
            await self.handle_order_cancelled(event)
