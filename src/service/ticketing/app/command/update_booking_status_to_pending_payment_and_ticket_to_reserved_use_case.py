from fastapi import Depends

from src.platform.database.unit_of_work import AbstractUnitOfWork, get_unit_of_work
from src.service.ticketing.domain.entity.booking_entity import Booking
from src.platform.logging.loguru_io import Logger


class UpdateBookingToPendingPaymentAndTicketToReservedUseCase:
    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    @classmethod
    def depends(cls, uow: AbstractUnitOfWork = Depends(get_unit_of_work)):
        return cls(uow=uow)

    @Logger.io
    async def execute(
        self, *, booking_id: int, buyer_id: int, ticket_ids: list[int]
    ) -> Booking | None:
        """
        執行訂單狀態更新為待付款

        Args:
            booking_id: 訂單 ID
            buyer_id: 買家 ID
            ticket_ids: 票券 ID 列表

        Returns:
            更新後的訂單，若失敗則返回 None

        Raises:
            無 - 錯誤通過返回 None 處理
        """
        async with self.uow:
            # 查詢訂單
            booking = await self.uow.booking_query_repo.get_by_id(booking_id=booking_id)
            if not booking:
                Logger.base.error(f'❌ 找不到訂單: booking_id={booking_id}')
                return None

            # 驗證所有權
            if booking.buyer_id != buyer_id:
                Logger.base.error(
                    f'❌ 訂單所有者不符: booking.buyer_id={booking.buyer_id}, event.buyer_id={buyer_id}'
                )
                return None

            # 更新狀態
            updated_booking = await self.uow.booking_command_repo.update_status_to_pending_payment(
                booking=booking
            )

            # UoW commits!
            await self.uow.commit()
            return updated_booking

    @Logger.io
    async def update_booking_status_to_pending_payment(self, *, booking: Booking) -> Booking:
        """
        舊方法 - 保留向後兼容性

        TODO: 逐步遷移到 execute() 方法
        """
        async with self.uow:
            updated_booking = await self.uow.booking_command_repo.update_status_to_pending_payment(
                booking=booking
            )
            await self.uow.commit()
            return updated_booking
