from typing import Any, Dict, List
from uuid import UUID


from src.service.ticketing.app.interface.i_booking_query_repo import IBookingQueryRepo
from src.platform.logging.loguru_io import Logger


class ListBookingsUseCase:
    def __init__(self, booking_query_repo: IBookingQueryRepo):
        self.booking_query_repo = booking_query_repo

    @Logger.io
    async def list_buyer_bookings(self, buyer_id: UUID, status: str) -> List[Dict[str, Any]]:
        bookings = await self.booking_query_repo.get_buyer_bookings_with_details(
            buyer_id=buyer_id, status=status
        )
        return bookings

    @Logger.io
    async def list_seller_bookings(self, seller_id: UUID, status: str) -> List[Dict[str, Any]]:
        bookings = await self.booking_query_repo.get_seller_bookings_with_details(
            seller_id=seller_id, status=status
        )
        return bookings
