"""
Booking Service 的事件處理器
"""

from typing import Any, Dict

from src.booking.port.booking_mq_gateway import BookingMqGateway
from src.shared.logging.loguru_io import Logger


class BookingEventConsumer:
    """處理 Booking Service 相關的事件"""

    def __init__(self):
        pass

    async def can_handle(self, event_type: str) -> bool:
        """檢查是否可以處理指定的事件類型"""
        return event_type in ['TicketsReserved', 'TicketReservationFailed']

    async def handle(self, event_data: Dict[str, Any]) -> bool:
        """處理事件，返回處理結果"""
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

            # 驗證必要欄位
            if buyer_id is None or booking_id is None or not ticket_ids:
                Logger.base.error('❌ [BOOKING Handler] 缺少必要欄位！')
                Logger.base.error(f'   buyer_id: {buyer_id} (is None: {buyer_id is None})')
                Logger.base.error(f'   booking_id: {booking_id} (is None: {booking_id is None})')
                Logger.base.error(f'   ticket_ids: {ticket_ids} (empty: {not ticket_ids})')
                return False

            # 使用 MQ Gateway 處理事件
            gateway = BookingMqGateway()
            success = await gateway.handle_tickets_reserved(
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
    async def _handle_reservation_failed(self, event_data: Dict[str, Any]) -> bool:
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

            # 使用 MQ Gateway 處理失敗事件
            gateway = BookingMqGateway()
            success = await gateway.handle_ticket_reservation_failed(
                booking_id=booking_id, buyer_id=buyer_id, error_message=error_message
            )

            return success

        except Exception as e:
            Logger.base.error(f'💥 [BOOKING Handler] 處理票券預訂失敗事件時發生錯誤: {e}')
            return False
