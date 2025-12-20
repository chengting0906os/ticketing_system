import random
import string
from datetime import datetime, timezone
from typing import Any, Self

from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from uuid_utils import UUID

from src.platform.config.di import Container
from src.platform.exception.exceptions import DomainError, ForbiddenError, NotFoundError
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.app.interface.i_booking_event_publisher import IBookingEventPublisher
from src.service.ticketing.domain.domain_event.booking_domain_event import BookingPaidEvent
from src.service.ticketing.domain.entity.booking_entity import BookingStatus


class MockPaymentAndUpdateBookingStatusToCompletedAndTicketToPaidUseCase:
    """Mock payment use case for testing"""

    def __init__(
        self,
        *,
        booking_command_repo: IBookingCommandRepo,
        event_publisher: IBookingEventPublisher,
    ) -> None:
        self.booking_command_repo = booking_command_repo
        self.event_publisher = event_publisher

    @classmethod
    @inject
    def depends(
        cls,
        booking_command_repo: IBookingCommandRepo = Depends(
            Provide[Container.booking_command_repo]
        ),
        event_publisher: IBookingEventPublisher = Depends(
            Provide[Container.booking_event_publisher]
        ),
    ) -> Self:
        return cls(booking_command_repo=booking_command_repo, event_publisher=event_publisher)

    @Logger.io
    async def pay_booking(
        self, booking_id: UUID, buyer_id: int, card_number: str
    ) -> dict[str, Any]:
        if not card_number:
            raise DomainError('Card number is required for payment')

        booking = await self.booking_command_repo.get_by_id(booking_id=booking_id)
        if not booking:
            raise NotFoundError('Booking not found')

        if booking.buyer_id != buyer_id:
            raise ForbiddenError('Only the buyer can pay for this booking')

        booking.validate_can_be_paid()

        tickets = await self.booking_command_repo.get_tickets_by_booking_id(booking_id=booking_id)
        ticket_ids: list[int] = [ticket.id for ticket in tickets if ticket.id is not None]

        completed_booking = booking.mark_as_completed()
        updated_booking = (
            await self.booking_command_repo.complete_booking_and_mark_tickets_sold_atomically(
                booking=completed_booking, ticket_ids=ticket_ids
            )
        )

        assert booking.seat_positions, 'Booking to pay must have seat_positions'

        await self.event_publisher.publish_booking_paid(
            event=BookingPaidEvent(
                booking_id=booking_id,
                buyer_id=buyer_id,
                event_id=booking.event_id,
                section=booking.section,
                subsection=booking.subsection,
                seat_positions=booking.seat_positions,
                paid_at=updated_booking.paid_at or datetime.now(timezone.utc),
                total_amount=float(sum(ticket.price for ticket in tickets)),
            )
        )

        payment_id = (
            f'PAY_MOCK_{"".join(random.choices(string.ascii_uppercase + string.digits, k=8))}'
        )

        return {
            'booking_id': updated_booking.id,
            'payment_id': payment_id,
            'status': BookingStatus.COMPLETED.value,
            'paid_at': updated_booking.paid_at.isoformat() if updated_booking.paid_at else None,
        }
