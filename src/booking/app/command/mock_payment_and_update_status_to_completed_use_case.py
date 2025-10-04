import random
import string
from typing import Any, Dict

from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.booking.app.interface.i_booking_command_repo import BookingCommandRepo
from src.booking.app.interface.i_booking_query_repo import BookingQueryRepo
from src.booking.domain.booking_domain_events import BookingPaidEvent
from src.booking.domain.booking_entity import BookingStatus
from src.platform.config.db_setting import get_async_session
from src.platform.config.di import Container
from src.platform.exception.exceptions import DomainError, ForbiddenError, NotFoundError
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.event_publisher import publish_domain_event
from src.platform.message_queue.kafka_constant_builder import KafkaTopicBuilder


class MockPaymentUseCase:
    def __init__(
        self,
        session: AsyncSession,
        booking_command_repo: BookingCommandRepo,
        booking_query_repo: BookingQueryRepo,
    ):
        self.session = session
        self.booking_command_repo: BookingCommandRepo = booking_command_repo  # pyright: ignore[reportAttributeAccessIssue]
        self.booking_query_repo: BookingQueryRepo = booking_query_repo  # pyright: ignore[reportAttributeAccessIssue]

    @classmethod
    @inject
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        booking_command_repo: BookingCommandRepo = Depends(Provide[Container.booking_command_repo]),
        booking_query_repo: BookingQueryRepo = Depends(Provide[Container.booking_query_repo]),
    ):
        return cls(
            session=session,
            booking_command_repo=booking_command_repo,
            booking_query_repo=booking_query_repo,
        )

    @Logger.io
    async def pay_booking(self, booking_id: int, buyer_id: int, card_number: str) -> Dict[str, Any]:
        # In a real implementation, card_number would be used for payment processing
        # For mock payment, we just validate it's present
        if not card_number:
            raise DomainError('Card number is required for payment')

        # Get the existing booking
        booking = await self.booking_query_repo.get_by_id(booking_id=booking_id)
        if not booking:
            raise NotFoundError('Booking not found')

        # Validate booking ownership and status
        if booking.buyer_id != buyer_id:
            raise ForbiddenError('Only the buyer can pay for this booking')

        if booking.status == BookingStatus.PAID:
            raise DomainError('Booking already paid')
        elif booking.status == BookingStatus.CANCELLED:
            raise DomainError('Cannot pay for cancelled booking')
        elif booking.status != BookingStatus.PENDING_PAYMENT:
            raise DomainError('Booking is not in a payable state')

        # Process payment and update booking
        paid_booking = booking.mark_as_paid()
        updated_booking = await self.booking_command_repo.update_status_to_paid(
            booking=paid_booking
        )

        # Publish domain event for event_ticketing service to handle ticket finalization
        reserved_tickets = await self.booking_query_repo.get_tickets_by_booking_id(
            booking_id=booking_id
        )
        if reserved_tickets:
            Logger.base.info(
                f'💳 [PAYMENT] Publishing payment event for {len(reserved_tickets)} tickets in booking {booking_id}'
            )

            # Extract ticket IDs
            ticket_ids = [ticket.id for ticket in reserved_tickets if ticket.id is not None]

            if ticket_ids:
                # Create and publish BookingPaidEvent
                from datetime import datetime, timezone

                paid_event = BookingPaidEvent(
                    booking_id=booking_id,
                    buyer_id=buyer_id,
                    event_id=booking.event_id,
                    ticket_ids=ticket_ids,
                    paid_at=updated_booking.paid_at or datetime.now(timezone.utc),
                    total_amount=float(sum(ticket.price for ticket in reserved_tickets)),
                )

                # Publish to event_ticketing service according to README pattern
                topic_name = KafkaTopicBuilder.update_ticket_status_to_paid_in_postgresql(
                    event_id=booking.event_id
                )
                partition_key = f'event-{booking.event_id}'

                await publish_domain_event(
                    event=paid_event, topic=topic_name, partition_key=partition_key
                )

                Logger.base.info(f'✅ [PAYMENT] Published BookingPaidEvent to topic: {topic_name}')

        # Generate mock payment ID
        payment_id = (
            f'PAY_MOCK_{"".join(random.choices(string.ascii_uppercase + string.digits, k=8))}'
        )

        # Commit the transaction
        await self.session.commit()

        return {
            'booking_id': updated_booking.id,
            'payment_id': payment_id,
            'status': 'paid',
            'paid_at': updated_booking.paid_at.isoformat() if updated_booking.paid_at else None,
        }
