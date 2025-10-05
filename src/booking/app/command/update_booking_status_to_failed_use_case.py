from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.booking.app.interface.i_booking_command_repo import BookingCommandRepo
from src.booking.app.interface.i_booking_query_repo import BookingQueryRepo
from src.booking.domain.booking_entity import Booking
from src.platform.config.db_setting import get_async_session
from src.platform.config.di import Container
from src.platform.logging.loguru_io import Logger


class UpdateBookingToFailedUseCase:
    def __init__(
        self,
        booking_command_repo: BookingCommandRepo,
        booking_query_repo: BookingQueryRepo,
        session: AsyncSession | None = None,
    ):
        self.booking_command_repo: BookingCommandRepo = booking_command_repo
        self.booking_query_repo: BookingQueryRepo = booking_query_repo
        self.session = session  # Optional for FastAPI compatibility

    @classmethod
    @inject
    def depends(
        cls,
        session: AsyncSession = Depends(get_async_session),
        booking_command_repo: BookingCommandRepo = Depends(Provide[Container.booking_command_repo]),
        booking_query_repo: BookingQueryRepo = Depends(Provide[Container.booking_query_repo]),
    ):
        return cls(
            session=session,
            booking_command_repo=booking_command_repo,
            booking_query_repo=booking_query_repo,
        )

    @Logger.io
    async def execute(
        self, *, booking_id: int, buyer_id: int, error_message: str | None = None
    ) -> Booking | None:
        """
        執行訂單狀態更新為失敗

        Args:
            booking_id: 訂單 ID
            buyer_id: 買家 ID
            error_message: 錯誤訊息 (可選)

        Returns:
            更新後的訂單，若失敗則返回 None
        """
        # 查詢訂單
        booking = await self.booking_query_repo.get_by_id(booking_id=booking_id)
        if not booking:
            Logger.base.error(f'❌ 找不到訂單: booking_id={booking_id}')
            return None

        # 驗證所有權
        if booking.buyer_id != buyer_id:
            Logger.base.error(
                f'❌ 訂單所有者不符: booking.buyer_id={booking.buyer_id}, event.buyer_id={buyer_id}'
            )
            return None

        # 標記為失敗狀態
        failed_booking = booking.mark_as_failed()  # type: ignore
        updated_booking = await self.booking_command_repo.update_status_to_failed(
            booking=failed_booking
        )

        Logger.base.info(f'✅ 訂單已標記為失敗: booking_id={booking_id}, error={error_message}')
        return updated_booking

    @Logger.io
    async def update_to_failed(self, booking: Booking) -> Booking:
        """
        舊方法 - 保留向後兼容性 (FastAPI 使用)

        TODO: 逐步遷移到 execute() 方法
        """
        # Use the domain method to transition to failed status
        failed_booking = booking.mark_as_failed()  # type: ignore
        updated_booking = await self.booking_command_repo.update_status_to_failed(
            booking=failed_booking
        )
        if self.session:
            await self.session.commit()
        return updated_booking
