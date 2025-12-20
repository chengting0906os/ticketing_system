from datetime import datetime, timezone
from typing import Self

from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from uuid_utils import UUID

from src.platform.config.di import Container
from src.platform.exception.exceptions import ForbiddenError, NotFoundError
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.app.interface.i_booking_event_publisher import IBookingEventPublisher
from src.service.ticketing.domain.domain_event.booking_domain_event import (
    BookingCancelledEvent,
)
from src.service.ticketing.domain.entity.booking_entity import Booking


class UpdateBookingToCancelledUseCase:
    """Update booking status to CANCELLED"""

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
        """Execute booking cancellation"""
        booking = await self.booking_command_repo.get_by_id(booking_id=booking_id)
        if not booking:
            raise NotFoundError('Booking not found')

        if booking.buyer_id != buyer_id:
            raise ForbiddenError('Only the buyer can cancel this booking')

        cancelled_booking = booking.cancel()
        updated_booking = await self.booking_command_repo.update_status_to_cancelled(
            booking=cancelled_booking
        )

        assert booking.seat_positions, 'Booking to cancel must have seat_positions'

        await self.event_publisher.publish_booking_cancelled(
            event=BookingCancelledEvent(
                booking_id=booking_id,
                buyer_id=buyer_id,
                event_id=booking.event_id,
                section=booking.section,
                subsection=booking.subsection,
                seat_positions=booking.seat_positions,
                cancelled_at=datetime.now(timezone.utc),
            )
        )

        return updated_booking
