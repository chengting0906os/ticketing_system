from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.service.ticketing.app.interface.i_booking_command_repo import BookingCommandRepo
from src.service.ticketing.domain.entity.booking_entity import Booking
from src.platform.config.db_setting import get_async_session
from src.platform.config.di import Container
from src.platform.logging.loguru_io import Logger


class UpdateBookingToPaidUseCase:
    def __init__(
        self,
        session: AsyncSession,
        booking_repo: BookingCommandRepo,
    ):
        self.session = session
        self.booking_repo: BookingCommandRepo = booking_repo  # pyright: ignore[reportAttributeAccessIssue]

    @classmethod
    @inject
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        booking_repo: BookingCommandRepo = Depends(Provide[Container.booking_command_repo]),
    ):
        return cls(session=session, booking_repo=booking_repo)

    @Logger.io
    async def update_booking_status_to_paid(self, *, booking: Booking) -> Booking:
        updated_booking = await self.booking_repo.update_status_to_paid(booking=booking)
        await self.session.commit()
        return updated_booking
