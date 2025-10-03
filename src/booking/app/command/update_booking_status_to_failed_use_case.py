from typing import TYPE_CHECKING

from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.booking.app.interface.i_booking_command_repo import BookingCommandRepo
from src.booking.domain.booking_entity import Booking
from src.platform.config.db_setting import get_async_session
from src.platform.config.di import Container
from src.platform.logging.loguru_io import Logger


if TYPE_CHECKING:
    from src.booking.driven_adapter.booking_command_repo_impl import BookingCommandRepoImpl


class UpdateBookingToFailedUseCase:
    def __init__(
        self,
        session: AsyncSession,
        booking_command_repo: BookingCommandRepo,
    ):
        self.session = session
        self.booking_command_repo: 'BookingCommandRepoImpl' = booking_command_repo  # pyright: ignore[reportAttributeAccessIssue]

    @classmethod
    @inject
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        booking_command_repo: BookingCommandRepo = Depends(Provide[Container.booking_command_repo]),
    ):
        return cls(session=session, booking_command_repo=booking_command_repo)

    @Logger.io
    async def update_to_failed(self, booking: Booking) -> Booking:
        """Update booking status to failed"""
        # Use the domain method to transition to failed status
        failed_booking = booking.mark_as_failed()  # type: ignore
        updated_booking = await self.booking_command_repo.update_status_to_failed(
            booking=failed_booking
        )
        await self.session.commit()
        return updated_booking
