from datetime import datetime, timezone
from uuid_utils import UUID
from src.platform.event.i_in_memory_broadcaster import IInMemoryEventBroadcaster
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface.i_booking_command_repo import IBookingCommandRepo
from src.service.ticketing.app.interface.i_booking_query_repo import IBookingQueryRepo
from src.service.ticketing.domain.entity.booking_entity import Booking


class UpdateBookingToFailedUseCase:
    """
    Update booking status to FAILED

    Dependencies:
    - booking_query_repo: For reading booking state
    - booking_command_repo: For updating booking status
    - event_broadcaster: For real-time SSE updates (optional)
    """

    def __init__(
        self,
        *,
        booking_query_repo: IBookingQueryRepo,
        booking_command_repo: IBookingCommandRepo,
        event_broadcaster: IInMemoryEventBroadcaster,
    ):
        self.booking_query_repo = booking_query_repo
        self.booking_command_repo = booking_command_repo
        self.event_broadcaster = event_broadcaster

    @Logger.io
    async def execute(
        self, *, booking_id: UUID, buyer_id: int, error_message: str | None = None
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

        # Broadcast SSE event for real-time updates
        try:
            await self.event_broadcaster.broadcast(
                booking_id=booking_id,
                event_data={
                    'event_type': 'status_update',
                    'booking_id': str(booking_id),
                    'status': 'failed',
                    'error_message': error_message,
                    'updated_at': datetime.now(timezone.utc).isoformat(),
                },
            )
            Logger.base.debug(f'📡 [SSE] Broadcasted failed status for booking {booking_id}')
        except Exception as e:
            # Don't fail use case if broadcast fails
            Logger.base.warning(f'⚠️ [SSE] Failed to broadcast event: {e}')

        return updated_booking

    @Logger.io
    async def update_to_failed(self, booking: Booking) -> Booking:
        """
        舊方法 - 保留向後兼容性 (FastAPI 使用)

        TODO: 逐步遷移到 execute() 方法
        """
        failed_booking = booking.mark_as_failed()  # type: ignore
        updated_booking = await self.booking_command_repo.update_status_to_failed(
            booking=failed_booking
        )
        return updated_booking
