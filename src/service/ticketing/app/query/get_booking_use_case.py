from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.service.ticketing.domain.entity.booking_entity import Booking
from src.service.ticketing.app.interface.i_booking_query_repo import IBookingQueryRepo
from src.platform.database.db_setting import get_async_read_session
from src.platform.config.di import Container
from src.platform.exception.exceptions import NotFoundError
from src.platform.logging.loguru_io import Logger


class GetBookingUseCase:
    def __init__(self, session: AsyncSession, booking_query_repo: IBookingQueryRepo):
        self.session = session
        self.booking_query_repo = booking_query_repo

    @classmethod
    @inject
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_read_session),
        booking_query_repo: IBookingQueryRepo = Depends(Provide[Container.booking_query_repo]),
    ):
        return cls(session=session, booking_query_repo=booking_query_repo)

    @Logger.io
    async def get_booking(self, booking_id: int) -> Booking:
        booking = await self.booking_query_repo.get_by_id(booking_id=booking_id)

        if not booking:
            raise NotFoundError('Booking not found')

        return booking

    @Logger.io
    async def get_booking_with_details(self, booking_id: int) -> dict:
        """Get booking with full details including event, user info, and tickets"""
        booking_details = await self.booking_query_repo.get_by_id_with_details(
            booking_id=booking_id
        )

        if not booking_details:
            raise NotFoundError('Booking not found')

        # Tickets are already included in booking_details via eager loading
        return booking_details
