from typing import TYPE_CHECKING

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.booking.domain.booking_command_repo import BookingCommandRepo
from src.booking.domain.booking_entity import Booking
from src.shared.config.db_setting import get_async_session
from src.shared.logging.loguru_io import Logger
from src.shared.service.repo_di import (
    get_booking_command_repo,
)


if TYPE_CHECKING:
    from src.booking.infra.booking_command_repo_impl import BookingCommandRepoImpl


class UpdateBookingToPendingPaymentUseCase:
    def __init__(
        self,
        session: AsyncSession,
        booking_command_repo: BookingCommandRepo,
    ):
        self.session = session
        self.booking_command_repo: 'BookingCommandRepoImpl' = booking_command_repo  # pyright: ignore[reportAttributeAccessIssue]

    @classmethod
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        booking_command_repo: BookingCommandRepo = Depends(get_booking_command_repo),
    ):
        return cls(session, booking_command_repo)

    @Logger.io
    async def update_to_pending_payment(self, booking: Booking) -> Booking:
        """Update booking status to pending payment"""
        pending_payment_booking = booking.mark_as_pending_payment()
        updated_booking = await self.booking_command_repo.update_status_to_pending_payment(
            booking=pending_payment_booking
        )
        await self.session.commit()
        return updated_booking
