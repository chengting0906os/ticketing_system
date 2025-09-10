"""Email notification use case for order domain events."""

from src.order.domain.events import (
    DomainEventProtocol,
    OrderCancelledEvent,
    OrderCreatedEvent,
    OrderPaidEvent,
)
from src.shared.logging.loguru_io import Logger
from src.shared.service.mock_email_service import MockEmailService


class MockSendEmailUseCase:
    def __init__(self, email_service: MockEmailService):
        self.email_service = email_service

    @Logger.io
    async def handle_order_created(self, event: OrderCreatedEvent):
        await self.email_service.send_order_confirmation(
            buyer_email=event.buyer_email,
            order_id=event.aggregate_id,
            product_name=event.product_name,
            price=event.price,
        )

        await self.email_service.notify_seller_new_order(
            seller_email=event.seller_email,
            order_id=event.aggregate_id,
            product_name=event.product_name,
            buyer_name=event.buyer_name,
            price=event.price,
        )

    @Logger.io
    async def handle_order_paid(self, event: OrderPaidEvent):
        await self.email_service.send_payment_confirmation(
            buyer_email=event.buyer_email,
            order_id=event.aggregate_id,
            product_name=event.product_name,
            paid_amount=event.paid_amount,
        )

    @Logger.io
    async def handle_order_cancelled(self, event: OrderCancelledEvent):
        await self.email_service.send_order_cancellation(
            buyer_email=event.buyer_email,
            order_id=event.aggregate_id,
            product_name=event.product_name,
        )

    @Logger.io
    async def handle_notification(self, event: DomainEventProtocol):
        if isinstance(event, OrderCreatedEvent):
            await self.handle_order_created(event)
        elif isinstance(event, OrderPaidEvent):
            await self.handle_order_paid(event)
        elif isinstance(event, OrderCancelledEvent):
            await self.handle_order_cancelled(event)
