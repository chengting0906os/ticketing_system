"""
Booking Service 的事件處理器
"""

from typing import Any, Dict

from src.shared.event_bus.event_consumer import EventHandler
from src.shared.logging.loguru_io import Logger


class BookingEventConsumer(EventHandler):
    """處理 Booking Service 相關的事件"""

    def __init__(self):
        self.session = None
        self.booking_query_repo = None
        self.update_pending_payment_use_case = None
        self._initialized = False

    async def _initialize_dependencies(self):
        """延遲初始化依賴項"""
        if not self._initialized:
            from src.booking.use_case.command.update_booking_status_to_pending_payment_use_case import (
                UpdateBookingToPendingPaymentUseCase,
            )
            from src.shared.config.db_setting import get_async_session
            from src.shared.service.repo_di import get_booking_command_repo, get_booking_query_repo

            self.session = await get_async_session().__anext__()
            self.booking_query_repo = get_booking_query_repo(self.session)
            self.update_pending_payment_use_case = UpdateBookingToPendingPaymentUseCase(
                session=self.session,
                booking_command_repo=get_booking_command_repo(self.session),
            )
            self._initialized = True

    async def can_handle(self, event_type: str) -> bool:
        """檢查是否可以處理指定的事件類型"""
        return event_type in ['TicketsReserved', 'TicketReservationFailed']

    async def handle(self, event_data: Dict[str, Any]) -> bool:
        """處理事件，返回處理結果"""
        await self._initialize_dependencies()

        try:
            event_type = event_data.get('event_type')
            Logger.base.info(f'📥 [BOOKING Handler] 收到事件: {event_type}')

            if event_type == 'TicketsReserved':
                Logger.base.info('🎫 [BOOKING Handler] 開始處理 TicketsReserved 事件')
                return await self._handle_tickets_reserved(event_data)
            elif event_type == 'TicketReservationFailed':
                Logger.base.info('❌ [BOOKING Handler] 開始處理 TicketReservationFailed 事件')
                return await self._handle_reservation_failed(event_data)
            else:
                Logger.base.warning(f'⚠️ [BOOKING Handler] 未知事件類型: {event_type}')
                return False

        except Exception as e:
            Logger.base.error(f'Error processing event: {e}')
            return False

    @Logger.io
    async def _handle_tickets_reserved(self, event_data: Dict[str, Any]) -> bool:
        """處理票券預訂成功事件，返回處理結果"""
        try:
            data = event_data.get('data', {})
            buyer_id = data.get('buyer_id')
            booking_id = data.get('booking_id')
            ticket_ids = data.get('ticket_ids', [])

            Logger.base.info(
                f'🔍 [BOOKING Handler] 解析票券預訂事件: booking_id={booking_id}, buyer_id={buyer_id}, ticket_ids={ticket_ids}'
            )

            if not all([buyer_id, booking_id, ticket_ids]):
                Logger.base.error('❌ [BOOKING Handler] 缺少必要欄位！')
                return False

            # 檢查依賴是否已初始化
            if not all([self.booking_query_repo, self.update_pending_payment_use_case]):
                Logger.base.error('❌ [BOOKING Handler] 依賴項未初始化！')
                return False

            # 獲取現有訂單
            Logger.base.info(f'🔎 [BOOKING Handler] 查詢預訂資料: booking_id={booking_id}')
            assert self.booking_query_repo is not None  # Type assertion for Pylance
            booking = await self.booking_query_repo.get_by_id(booking_id=booking_id)
            if not booking:
                Logger.base.error(f'❌ [BOOKING Handler] 預訂不存在: booking_id={booking_id}')
                return False

            # 驗證訂單所有權
            if booking.buyer_id != buyer_id:
                Logger.base.error(
                    f'❌ [BOOKING Handler] 訂單所有權驗證失敗: booking_id={booking_id}, expected_buyer={buyer_id}, actual_buyer={booking.buyer_id}'
                )
                return False

            # 更新訂單狀態
            Logger.base.info('⚡ [BOOKING Handler] 開始更新訂單狀態為 pending_payment...')
            assert self.update_pending_payment_use_case is not None  # Type assertion for Pylance
            await self.update_pending_payment_use_case.update_to_pending_payment(booking)

            Logger.base.info(f'✅ [BOOKING Handler] 訂單狀態更新成功: booking_id={booking_id}')
            return True

        except Exception as e:
            Logger.base.error(f'💥 [BOOKING Handler] 處理票券預訂事件時發生錯誤: {e}')
            return False

    @Logger.io
    async def _handle_reservation_failed(self, event_data: Dict[str, Any]) -> bool:
        """處理票券預訂失敗事件，返回處理結果"""
        try:
            data = event_data.get('data', {})
            request_id = data.get('request_id')
            error_message = data.get('error_message')
            booking_id = data.get('booking_id')

            Logger.base.info(
                f'🔍 [BOOKING Handler] 解析票券預訂失敗事件: request_id={request_id}, booking_id={booking_id}, error={error_message}'
            )

            Logger.base.warning(f'⚠️ [BOOKING Handler] 票券預訂失敗: {error_message}')

            # TODO: 實現失敗通知邏輯
            Logger.base.info('📋 [BOOKING Handler] TODO: 實現訂單失敗通知邏輯')
            return True  # 失敗事件處理成功

        except Exception as e:
            Logger.base.error(f'💥 [BOOKING Handler] 處理票券預訂失敗事件時發生錯誤: {e}')
            return False
