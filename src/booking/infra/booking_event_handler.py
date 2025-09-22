"""
Booking Service 的事件處理器
"""

from typing import Any, Dict

from src.booking.use_case.command.update_booking_status_to_pending_payment_use_case import (
    UpdateBookingToPendingPaymentUseCase,
)
from src.shared.config.db_setting import get_async_session
from src.shared.event_bus.event_consumer import EventHandler
from src.shared.logging.loguru_io import Logger
from src.shared.service.repo_di import get_booking_command_repo, get_booking_query_repo


class BookingEventHandler(EventHandler):
    """處理 Booking Service 相關的事件"""

    def __init__(self):
        self.session = None
        self.booking_command_repo = None
        self.booking_query_repo = None
        self.update_pending_payment_use_case = None
        self._initialized = False

    async def _ensure_initialized(self):
        """確保依賴項已初始化"""
        if not self._initialized:
            self.session = await get_async_session().__anext__()
            self.booking_command_repo = get_booking_command_repo(self.session)
            self.booking_query_repo = get_booking_query_repo(self.session)

            self.update_pending_payment_use_case = UpdateBookingToPendingPaymentUseCase(
                session=self.session,
                booking_command_repo=self.booking_command_repo,
            )
            self._initialized = True

    async def can_handle(self, event_type: str) -> bool:
        """檢查是否可以處理指定的事件類型"""
        return event_type in ['TicketsReserved', 'TicketReservationFailed']

    async def handle(self, event_data: Dict[str, Any]) -> None:
        """處理事件"""
        await self._ensure_initialized()

        event_type = event_data.get('event_type')
        print(f'\033[95m🔄 [BOOKING Handler] 收到響應事件: {event_type}\033[0m')
        Logger.base.info(f'🔄 [BOOKING Handler] 收到響應事件: {event_type}')

        if event_type == 'TicketsReserved':
            print('\033[92m🎉 [BOOKING Handler] 處理票務預留成功事件\033[0m')
            Logger.base.info('🎉 [BOOKING Handler] 處理票務預留成功事件')
            await self._handle_tickets_reserved(event_data)
        elif event_type == 'TicketReservationFailed':
            print('\033[91m❌ [BOOKING Handler] 處理票務預留失敗事件\033[0m')
            Logger.base.info('❌ [BOOKING Handler] 處理票務預留失敗事件')
            await self._handle_reservation_failed(event_data)

    @Logger.io
    async def _handle_tickets_reserved(self, event_data: Dict[str, Any]):
        try:
            data = event_data.get('data', {})
            buyer_id = data.get('buyer_id')
            booking_id = data.get('booking_id')
            ticket_ids = data.get('ticket_ids', [])

            print(
                f'\033[96m🔍 [BOOKING Handler] 解析 TicketsReserved 事件: booking_id={booking_id}, buyer_id={buyer_id}, ticket_ids={ticket_ids}\033[0m'
            )
            Logger.base.info(
                f'🔍 [BOOKING Handler] 解析 TicketsReserved 事件: booking_id={booking_id}, buyer_id={buyer_id}, ticket_ids={ticket_ids}'
            )

            if not all([buyer_id, booking_id, ticket_ids]):
                print('\033[91m❌ [BOOKING Handler] 缺少必要欄位！\033[0m')
                Logger.base.info('❌ [BOOKING Handler] 缺少必要欄位！')
                Logger.base.error('Missing required fields in tickets reserved event')
                return

            # 獲取現有的預訂
            if not self.booking_query_repo:
                Logger.base.error('BookingQueryRepo not initialized')
                return

            print(f'\033[94m🔎 [BOOKING Handler] 查詢預訂狀態: booking_id={booking_id}\033[0m')
            Logger.base.info(f'🔎 [BOOKING Handler] 查詢預訂狀態: booking_id={booking_id}')
            booking = await self.booking_query_repo.get_by_id(booking_id=booking_id)
            if not booking:
                print(f'\033[91m❌ [BOOKING Handler] 預訂不存在！booking_id={booking_id}\033[0m')
                Logger.base.info(f'❌ [BOOKING Handler] 預訂不存在！booking_id={booking_id}')
                Logger.base.error(f'Booking {booking_id} not found')
                return

            print(f'\033[93m📊 [BOOKING Handler] 當前預訂狀態: {booking.status.value}\033[0m')
            Logger.base.info(f'📊 [BOOKING Handler] 當前預訂狀態: {booking.status.value}')

            # 驗證預訂是否屬於該買家
            if booking.buyer_id != buyer_id:
                print('\033[91m❌ [BOOKING Handler] 預訂不屬於該買家！\033[0m')
                Logger.base.info('❌ [BOOKING Handler] 預訂不屬於該買家！')
                Logger.base.error(f'Booking {booking_id} does not belong to buyer {buyer_id}')
                return

            # 將預訂狀態從 PROCESSING 更新為 PENDING_PAYMENT
            if not self.update_pending_payment_use_case:
                Logger.base.error('UpdateBookingToPendingPaymentUseCase not initialized')
                return

            print('\033[95m⚡ [BOOKING Handler] 更新預訂狀態: PROCESSING → PENDING_PAYMENT\033[0m')
            Logger.base.info('⚡ [BOOKING Handler] 更新預訂狀態: PROCESSING → PENDING_PAYMENT')
            await self.update_pending_payment_use_case.update_to_pending_payment(booking)

            print(
                f'\033[92m🎊 [BOOKING Handler] 預訂狀態更新完成！booking_id={booking_id} 現在可以進行付款\033[0m'
            )
            Logger.base.info(
                f'🎊 [BOOKING Handler] 預訂狀態更新完成！booking_id={booking_id} 現在可以進行付款'
            )
            Logger.base.info(f'Updated booking {booking_id} status to pending_payment')

        except Exception as e:
            Logger.base.error(f'Error handling tickets reserved: {e}')

    @Logger.io
    async def _handle_reservation_failed(self, event_data: Dict[str, Any]):
        """處理票務預留失敗事件"""
        try:
            data = event_data.get('data', {})
            request_id = data.get('request_id')
            error_message = data.get('error_message')

            Logger.base.warning(
                f'Ticket reservation failed for request {request_id}: {error_message}'
            )

            # TODO: 通知用戶失敗
            # 這可以觸發電子郵件通知、更新UI等

        except Exception as e:
            Logger.base.error(f'Error handling reservation failed: {e}')
