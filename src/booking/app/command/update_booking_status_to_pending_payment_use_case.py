from typing import TYPE_CHECKING

from dependency_injector.wiring import Provide, inject
from fastapi import Depends

from src.booking.app.interface.i_booking_command_repo import BookingCommandRepo
from src.booking.domain.booking_entity import Booking
from src.platform.config.di import Container
from src.platform.logging.loguru_io import Logger


if TYPE_CHECKING:
    from src.booking.driven_adapter.booking_command_repo_impl import BookingCommandRepoImpl


class UpdateBookingToPendingPaymentUseCase:
    def __init__(self, booking_command_repo: BookingCommandRepo):
        self.booking_command_repo: 'BookingCommandRepoImpl' = booking_command_repo  # pyright: ignore[reportAttributeAccessIssue]

    @classmethod
    @inject
    def depends(
        cls,
        booking_command_repo: BookingCommandRepo = Depends(Provide[Container.booking_command_repo]),
    ):
        return cls(booking_command_repo=booking_command_repo)

    @Logger.io
    async def update_booking_status_to_pending_payment(self, *, booking: Booking) -> Booking:
        # Repository handles its own session management through session_factory
        updated_booking = await self.booking_command_repo.update_status_to_pending_payment(
            booking=booking
        )
        return updated_booking
