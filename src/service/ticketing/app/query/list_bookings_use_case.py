from typing import Any, Dict, List

from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.service.ticketing.app.interface.i_booking_query_repo import IBookingQueryRepo
from src.platform.config.db_setting import get_async_session
from src.platform.config.di import Container
from src.platform.logging.loguru_io import Logger


class ListBookingsUseCase:
    def __init__(self, session: AsyncSession, booking_query_repo: IBookingQueryRepo):
        self.session = session
        self.booking_query_repo = booking_query_repo

    @classmethod
    @inject
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        booking_query_repo: IBookingQueryRepo = Depends(Provide[Container.booking_query_repo]),
    ):
        return cls(session=session, booking_query_repo=booking_query_repo)

    @Logger.io
    async def list_buyer_bookings(self, buyer_id: int, status: str) -> List[Dict[str, Any]]:
        bookings = await self.booking_query_repo.get_buyer_bookings_with_details(
            buyer_id=buyer_id, status=status
        )
        return bookings

    @Logger.io
    async def list_seller_bookings(self, seller_id: int, status: str) -> List[Dict[str, Any]]:
        bookings = await self.booking_query_repo.get_seller_bookings_with_details(
            seller_id=seller_id, status=status
        )
        return bookings
