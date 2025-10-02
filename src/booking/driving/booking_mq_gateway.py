"""
Booking MQ Gateway
處理來自事件系統的訂單相關請求，負責依賴注入和 session 管理
"""

from typing import Any, Dict, List

from src.booking.use_case.command.update_booking_status_to_pending_payment_use_case import (
    UpdateBookingToPendingPaymentUseCase,
)
from src.platform.config.di import container
from src.platform.logging.loguru_io import Logger


class BookingMqGateway:
    def __init__(self):
        pass

    async def can_handle(self, event_type: str) -> bool:
        """基於 topic 路由，所有進來的事件都能處理"""
        return True

    async def handle(self, event_data: Dict[str, Any]) -> bool:
        """
        處理事件數據 - 基於 topic 路由，不再判斷事件類型

        Args:
            event_data: 事件數據

        Returns:
            處理結果
        """
        try:
            # 直接處理數據，不再判斷事件類型
            data = event_data.get('data', {})
            booking_id = data.get('booking_id')
            buyer_id = data.get('buyer_id')

            Logger.base.info(
                f'📥 [BOOKING Handler] 處理事件: booking_id={booking_id}, buyer_id={buyer_id}'
            )

            # 檢查是否為失敗事件（包含 error_message 或 status='failed'）
            error_message = data.get('error_message')
            status = data.get('status')

            if error_message or status in ['failed', 'seat_reservation_failed']:
                Logger.base.info('❌ [BOOKING Handler] 處理失敗事件')
                return await self.handle_ticket_reservation_failed(
                    booking_id=booking_id, buyer_id=buyer_id, error_message=error_message
                )
            else:
                # 處理成功事件（有 ticket_ids）
                ticket_ids = data.get('ticket_ids', [])
                Logger.base.info('✅ [BOOKING Handler] 處理成功事件')
                return await self.handle_tickets_reserved(
                    booking_id=booking_id, buyer_id=buyer_id, ticket_ids=ticket_ids
                )

        except Exception as e:
            Logger.base.error(f'❌ [BOOKING Handler] 處理事件時發生錯誤: {e}')
            return False

    @Logger.io
    async def _handle_tickets_reserved_event(self, event_data: Dict[str, Any]) -> bool:
        """處理票券預訂成功事件，返回處理結果"""
        try:
            data = event_data.get('data', {})
            buyer_id = data.get('buyer_id')
            booking_id = data.get('booking_id')
            ticket_ids = data.get('ticket_ids', [])

            Logger.base.info(
                f'🔍 [BOOKING Handler] 解析票券預訂事件: booking_id={booking_id}, buyer_id={buyer_id}, ticket_ids={ticket_ids}'
            )

            # 驗證必要欄位
            if buyer_id is None or booking_id is None or not ticket_ids:
                Logger.base.error('❌ [BOOKING Handler] 缺少必要欄位！')
                Logger.base.error(f'   buyer_id: {buyer_id} (is None: {buyer_id is None})')
                Logger.base.error(f'   booking_id: {booking_id} (is None: {booking_id is None})')
                Logger.base.error(f'   ticket_ids: {ticket_ids} (empty: {not ticket_ids})')
                return False

            # 調用業務邏輯
            success = await self.handle_tickets_reserved(
                booking_id=booking_id, buyer_id=buyer_id, ticket_ids=ticket_ids
            )

            if success:
                Logger.base.info(f'✅ [BOOKING Handler] 訂單狀態更新成功: booking_id={booking_id}')
            else:
                Logger.base.error(f'❌ [BOOKING Handler] 訂單狀態更新失敗: booking_id={booking_id}')

            return success

        except Exception as e:
            Logger.base.error(f'💥 [BOOKING Handler] 處理票券預訂事件時發生錯誤: {e}')
            return False

    @Logger.io
    async def _handle_reservation_failed_event(self, event_data: Dict[str, Any]) -> bool:
        """處理票券預訂失敗事件，返回處理結果"""
        try:
            data = event_data.get('data', {})
            booking_id = data.get('booking_id')
            buyer_id = data.get('buyer_id')
            error_message = data.get('error_message')

            Logger.base.info(
                f'🔍 [BOOKING Handler] 解析票券預訂失敗事件: booking_id={booking_id}, '
                f'buyer_id={buyer_id}, error={error_message}'
            )

            # 調用業務邏輯
            success = await self.handle_ticket_reservation_failed(
                booking_id=booking_id, buyer_id=buyer_id, error_message=error_message
            )

            return success

        except Exception as e:
            Logger.base.error(f'💥 [BOOKING Handler] 處理票券預訂失敗事件時發生錯誤: {e}')
            return False

    @Logger.io
    async def handle_tickets_reserved(
        self, booking_id: int, buyer_id: int, ticket_ids: List[int]
    ) -> bool:
        try:
            # 取得 repositories 和 use case 使用 DI container
            cmd_repo = container.booking_command_repo()
            query_repo = container.booking_query_repo()
            update_use_case = UpdateBookingToPendingPaymentUseCase(cmd_repo)

            # 查詢訂單
            booking = await query_repo.get_by_id(booking_id=booking_id)
            if not booking:
                Logger.base.error(f'❌ 找不到訂單: booking_id={booking_id}')
                return False

            # 驗證所有權
            if booking.buyer_id != buyer_id:
                Logger.base.error(
                    f'❌ 訂單所有者不符: booking.buyer_id={booking.buyer_id}, event.buyer_id={buyer_id}'
                )
                return False

            # 使用 use case 更新狀態 (不需要傳遞 session)
            await update_use_case.update_booking_status_to_pending_payment(booking=booking)

            Logger.base.info(f'✅ 訂單狀態已更新為待付款: booking_id={booking_id}')
            return True

        except Exception as e:
            Logger.base.error(f'❌ 處理票券預訂事件失敗: {e}')
            return False

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
