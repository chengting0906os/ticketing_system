import random
import string
from uuid_utils import UUID
from typing import Any, Dict

from dependency_injector.wiring import Provide, inject
from fastapi import Depends

from src.platform.config.di import Container
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.domain.domain_event.booking_domain_event import BookingPaidEvent
from src.service.ticketing.domain.entity.booking_entity import BookingStatus
from src.platform.exception.exceptions import DomainError, ForbiddenError, NotFoundError
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.event_publisher import publish_domain_event
from src.platform.message_queue.kafka_constant_builder import KafkaTopicBuilder


class MockPaymentAndUpdateBookingStatusToCompletedAndTicketToPaidUseCase:
    def __init__(
        self,
        *,
        booking_command_repo: IBookingCommandRepo,
    ):
        self.booking_command_repo = booking_command_repo

    @classmethod
    @inject
    def depends(
        cls,
        booking_command_repo: IBookingCommandRepo = Depends(
            Provide[Container.booking_command_repo]
        ),
    ):
        """For FastAPI endpoint compatibility"""
        return cls(booking_command_repo=booking_command_repo)

    @Logger.io
    async def pay_booking(
        self, booking_id: UUID, buyer_id: int, card_number: str
    ) -> Dict[str, Any]:
        # In a real implementation, card_number would be used for payment processing
        # For mock payment, we just validate it's present
        if not card_number:
            raise DomainError('Card number is required for payment')

        # Get the existing booking
        booking = await self.booking_command_repo.get_by_id(booking_id=booking_id)
        if not booking:
            raise NotFoundError('Booking not found')

        # Validate booking ownership and payment eligibility (domain logic)
        if booking.buyer_id != buyer_id:
            raise ForbiddenError('Only the buyer can pay for this booking')

        # Use domain method to validate payment eligibility
        booking.validate_can_be_paid()

        # Get reserved tickets first (before transaction)
        reserved_tickets = await self.booking_command_repo.get_tickets_by_booking_id(
            booking_id=booking_id
        )

        # Extract ticket IDs for status update
        ticket_ids = [ticket.id for ticket in reserved_tickets if ticket.id is not None]

        # Process payment - atomically update booking AND tickets in single transaction
        completed_booking = booking.mark_as_completed()
        updated_booking = (
            await self.booking_command_repo.complete_booking_and_mark_tickets_sold_atomically(
                booking=completed_booking, ticket_ids=ticket_ids
            )
        )

        Logger.base.info(
            f'💳 [PAYMENT] Atomically completed booking {booking_id} and marked {len(ticket_ids)} tickets as SOLD'
        )

        # Publish domain event after successful commit
        if reserved_tickets:
            Logger.base.info(
                f'💳 [PAYMENT] Publishing payment event for {len(reserved_tickets)} tickets in booking {booking_id}'
            )

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

                # Publish to seat_reservation service to finalize payment in Kvrocks
                topic_name = KafkaTopicBuilder.finalize_ticket_status_to_paid_in_kvrocks(
                    event_id=booking.event_id
                )
                partition_key = f'event-{booking.event_id}'

                await publish_domain_event(
                    event=paid_event, topic=topic_name, partition_key=partition_key
                )

                Logger.base.info(
                    f'✅ [PAYMENT] Published BookingPaidEvent to finalize in Kvrocks: {topic_name}'
                )

        # Generate mock payment ID
        payment_id = (
            f'PAY_MOCK_{"".join(random.choices(string.ascii_uppercase + string.digits, k=8))}'
        )

        return {
            'booking_id': updated_booking.id,
            'payment_id': payment_id,
            'status': BookingStatus.COMPLETED.value,
            'paid_at': updated_booking.paid_at.isoformat() if updated_booking.paid_at else None,
        }
