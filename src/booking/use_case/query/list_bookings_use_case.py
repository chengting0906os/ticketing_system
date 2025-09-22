from typing import Any, Dict, List

from fastapi import Depends

from src.shared.logging.loguru_io import Logger
from src.shared.service.unit_of_work import AbstractUnitOfWork, get_unit_of_work


class ListBookingsUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow=uow)

    @Logger.io
    async def list_buyer_bookings(self, buyer_id: int, status: str) -> List[Dict[str, Any]]:
        async with self.uow:
            bookings = await self.uow.bookings.get_buyer_bookings_with_details(
                buyer_id=buyer_id, status=status
            )
            return bookings

    @Logger.io
    async def list_seller_bookings(self, seller_id: int, status: str) -> List[Dict[str, Any]]:
        async with self.uow:
            bookings = await self.uow.bookings.get_seller_bookings_with_details(
                seller_id=seller_id, status=status
            )
            return bookings
