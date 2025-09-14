from src.booking.domain.events import (
    BookingCancelledEvent,
    BookingCreatedEvent,
    BookingPaidEvent,
    DomainEventProtocol,
)
from src.shared.logging.loguru_io import Logger
from src.shared.service.mock_email_service import MockEmailService


class MockSendEmailUseCase:
    def __init__(self, email_service: MockEmailService):
        self.email_service = email_service

    @Logger.io
    async def handle_booking_created(self, event: BookingCreatedEvent):
        await self.email_service.send_booking_confirmation(
            buyer_email=event.buyer_email,
            booking_id=event.aggregate_id,
            event_name=event.event_name,
            price=event.price,
        )

        await self.email_service.notify_seller_new_booking(
            seller_email=event.seller_email,
            booking_id=event.aggregate_id,
            event_name=event.event_name,
            buyer_name=event.buyer_name,
            price=event.price,
        )

    @Logger.io
    async def handle_booking_paid(self, event: BookingPaidEvent):
        await self.email_service.send_payment_confirmation(
            buyer_email=event.buyer_email,
            booking_id=event.aggregate_id,
            event_name=event.event_name,
            paid_amount=event.paid_amount,
        )

    @Logger.io
    async def handle_booking_cancelled(self, event: BookingCancelledEvent):
        await self.email_service.send_booking_cancellation(
            buyer_email=event.buyer_email,
            booking_id=event.aggregate_id,
            event_name=event.event_name,
        )

    @Logger.io
    async def handle_notification(self, event: DomainEventProtocol):
        if isinstance(event, BookingCreatedEvent):
            await self.handle_booking_created(event)
        elif isinstance(event, BookingPaidEvent):
            await self.handle_booking_paid(event)
        elif isinstance(event, BookingCancelledEvent):
            await self.handle_booking_cancelled(event)
