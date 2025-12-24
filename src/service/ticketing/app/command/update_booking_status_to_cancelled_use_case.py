from typing import Self

from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from uuid_utils import UUID

from src.platform.config.di import Container
from src.platform.exception.exceptions import DomainError, ForbiddenError, NotFoundError
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.app.interface.i_booking_event_publisher import IBookingEventPublisher
from src.service.ticketing.domain.domain_event.booking_domain_event import (
    BookingCancelledEvent,
)
from src.service.ticketing.domain.entity.booking_entity import Booking


class UpdateBookingToCancelledUseCase:
    """
    Request booking cancellation.

    This use case validates the cancellation request and publishes
    BookingCancelledEvent. The actual DB update is handled by
    Reservation Service after releasing seats in Kvrocks.

    Flow:
    1. Validate booking exists and buyer owns it
    2. Publish BookingCancelledEvent to Kafka
    3. Reservation Service receives event:
       - Release seats in Kvrocks
       - Update booking → CANCELLED in PostgreSQL
       - Update tickets → AVAILABLE in PostgreSQL
    """

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
    async def execute(self, *, booking_id: UUID, buyer_id: int) -> Booking:
        """
        Execute booking cancellation request.

        Note: Returns the booking with original status.
        The actual CANCELLED status update happens asynchronously
        in Reservation Service after Kvrocks seats are released.
        """
        booking = await self.booking_command_repo.get_by_id(booking_id=booking_id)
        if not booking:
            raise NotFoundError('Booking not found')

        if booking.buyer_id != buyer_id:
            raise ForbiddenError('Only the buyer can cancel this booking')

        # Validate booking can be cancelled (only PROCESSING or PENDING_PAYMENT)
        terminal_states = ('cancelled', 'completed', 'failed')
        if booking.status.value in terminal_states:
            if booking.status.value == 'completed':
                raise DomainError('Cannot cancel a completed booking')
            elif booking.status.value == 'failed':
                raise DomainError('Cannot cancel failed booking')
            else:  # cancelled
                raise DomainError('Booking is already cancelled')

        assert booking.seat_positions, 'Booking to cancel must have seat_positions'

        # Publish minimal event - Reservation Service fetches details from DB
        await self.event_publisher.publish_booking_cancelled(
            event=BookingCancelledEvent(
                booking_id=booking_id,
                event_id=booking.event_id,
                section=booking.section,
                subsection=booking.subsection,
            )
        )

        Logger.base.info(f'📤 [CANCEL] Published BookingCancelledEvent for booking {booking_id}')

        # Return booking with pending cancellation
        # Actual status change happens in Reservation Service
        return booking.cancel()
