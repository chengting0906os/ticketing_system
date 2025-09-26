"""
Booking MQ Gateway
處理來自事件系統的訂單相關請求，負責依賴注入和 session 管理
"""

from typing import List

from src.booking.use_case.command.update_booking_status_to_pending_payment_use_case import (
    UpdateBookingToPendingPaymentUseCase,
)
from src.shared.config.db_setting import async_session_maker
from src.shared.logging.loguru_io import Logger
from src.shared.service.repo_di import get_booking_command_repo, get_booking_query_repo


class BookingMqGateway:
    def __init__(self):
        pass

    @Logger.io
    async def handle_tickets_reserved(
        self, booking_id: int, buyer_id: int, ticket_ids: List[int]
    ) -> bool:
        session = async_session_maker()

        try:
            # 取得 repositories
            booking_command_repo = get_booking_command_repo(session)
            booking_query_repo = get_booking_query_repo(session)

            # 查詢訂單
            booking = await booking_query_repo.get_by_id(booking_id=booking_id)
            if not booking:
                Logger.base.error(f'❌ 找不到訂單: booking_id={booking_id}')
                return False

            # 驗證所有權
            if booking.buyer_id != buyer_id:
                Logger.base.error(
                    f'❌ 訂單所有者不符: booking.buyer_id={booking.buyer_id}, event.buyer_id={buyer_id}'
                )
                return False

            # 使用 use case 更新狀態
            update_use_case = UpdateBookingToPendingPaymentUseCase(session, booking_command_repo)
            await update_use_case.update_to_pending_payment(booking)

            Logger.base.info(f'✅ 訂單狀態已更新為待付款: booking_id={booking_id}')
            return True

        except Exception as e:
            Logger.base.error(f'❌ 處理票券預訂事件失敗: {e}')
            await session.rollback()
            return False
        finally:
            # 確保 session 被關閉
            await session.close()

    @Logger.io
    async def handle_ticket_reservation_failed(
        self, booking_id: int, buyer_id: int, error_message: str
    ) -> bool:
        """處理票券預訂失敗事件"""
        Logger.base.warning(f'⚠️ 票券預訂失敗: booking_id={booking_id}, error={error_message}')

        # TODO: 實現訂單失敗處理邏輯
        # 可以創建一個 UpdateBookingToFailedUseCase
        Logger.base.info('📋 TODO: 實現訂單失敗處理邏輯')

        return True  # 失敗事件處理成功
