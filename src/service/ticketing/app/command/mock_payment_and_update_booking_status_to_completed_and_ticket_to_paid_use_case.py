import random
import string
from typing import Any, Self

from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from uuid_utils import UUID

from src.platform.config.di import Container
from src.platform.exception.exceptions import DomainError, ForbiddenError, NotFoundError
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.domain.entity.booking_entity import BookingStatus


class MockPaymentAndUpdateBookingStatusToCompletedAndTicketToPaidUseCase:
    """Mock payment use case for testing"""

    def __init__(
        self,
        *,
        booking_command_repo: IBookingCommandRepo,
    ) -> None:
        self.booking_command_repo = booking_command_repo

    @classmethod
    @inject
    def depends(
        cls,
        booking_command_repo: IBookingCommandRepo = Depends(
            Provide[Container.booking_command_repo]
        ),
    ) -> Self:
        return cls(booking_command_repo=booking_command_repo)

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

        # Note: No Kafka event needed - Kvrocks only tracks AVAILABLE/RESERVED states
        # PostgreSQL is the source of truth for SOLD/COMPLETED status

        payment_id = (
            f'PAY_MOCK_{"".join(random.choices(string.ascii_uppercase + string.digits, k=8))}'
        )

        return {
            'booking_id': updated_booking.id,
            'payment_id': payment_id,
            'status': BookingStatus.COMPLETED.value,
            'paid_at': updated_booking.paid_at.isoformat() if updated_booking.paid_at else None,
        }
