from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.booking.domain.booking_entity import Booking
from src.booking.domain.booking_query_repo import BookingQueryRepo
from src.shared.config.db_setting import get_async_session
from src.shared.exception.exceptions import NotFoundError
from src.shared.logging.loguru_io import Logger
from src.shared.service.repo_di import get_booking_query_repo


class GetBookingUseCase:
    def __init__(self, session: AsyncSession, booking_query_repo: BookingQueryRepo):
        self.session = session
        self.booking_query_repo = booking_query_repo

    @classmethod
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        booking_query_repo: BookingQueryRepo = Depends(get_booking_query_repo),
    ):
        return cls(session=session, booking_query_repo=booking_query_repo)

    @Logger.io
    async def get_booking(self, booking_id: int) -> Booking:
        booking = await self.booking_query_repo.get_by_id(booking_id=booking_id)

        if not booking:
            raise NotFoundError('Booking not found')

        return booking
