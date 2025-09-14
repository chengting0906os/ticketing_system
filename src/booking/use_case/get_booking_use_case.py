from fastapi import Depends

from src.booking.domain.booking_entity import Booking
from src.shared.exception.exceptions import NotFoundError
from src.shared.logging.loguru_io import Logger
from src.shared.service.unit_of_work import AbstractUnitOfWork, get_unit_of_work


class GetBookingUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow=uow)

    @Logger.io
    async def get_booking(self, booking_id: int) -> Booking:
        async with self.uow:
            booking = await self.uow.bookings.get_by_id(booking_id=booking_id)

            if not booking:
                raise NotFoundError('Booking not found')

            return booking
