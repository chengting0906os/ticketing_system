"""
Seat Reservation Consumer
座位預訂服務的 Kafka 消費者
負責接收預訂請求並協調處理流程
"""

import asyncio
from typing import Any, Dict

from src.seat_reservation.use_case.reserve_seats_use_case import (
    ReservationRequest,
    ReserveSeatsUseCase,
    create_reserve_seats_use_case,
)
from src.shared.logging.loguru_io import Logger
from src.shared.message_queue.unified_mq_consumer import UnifiedEventConsumer


class SeatReservationEventHandler:
    """
    座位預訂事件處理器

    處理來自 booking_service 的預訂請求
    """

    def __init__(self, reserve_use_case: ReserveSeatsUseCase):
        self.reserve_use_case = reserve_use_case

    @Logger.io
    async def can_handle(self, event_type: str) -> bool:
        """檢查是否能處理此事件類型"""
        supported_events = ['BookingCreated', 'SeatReservationRequest', 'SeatReleaseRequest']
        return event_type in supported_events

    @Logger.io
    async def handle(self, event_data: Dict[str, Any]) -> bool:
        """
        處理事件

        Args:
            event_data: 事件數據

        Returns:
            bool: 處理是否成功
        """
        event_type = event_data.get('event_type')

        try:
            if event_type == 'BookingCreated':
                return await self._handle_booking_created(event_data)
            elif event_type == 'SeatReservationRequest':
                return await self._handle_seat_reservation_request(event_data)
            elif event_type == 'SeatReleaseRequest':
                return await self._handle_seat_release_request(event_data)
            else:
                Logger.base.warning(f'⚠️ [SEAT_HANDLER] Unsupported event type: {event_type}')
                return False

        except Exception as e:
            Logger.base.error(f'❌ [SEAT_HANDLER] Error handling {event_type}: {e}')
            return False

    async def _handle_booking_created(self, event_data: Dict[str, Any]) -> bool:
        """
        處理訂單創建事件

        當 booking_service 創建訂單後，需要預訂座位
        """
        data = event_data.get('data', {})

        booking_id = data.get('booking_id')
        buyer_id = data.get('buyer_id')
        event_id = data.get('event_id')
        seat_selection_mode = data.get('seat_selection_mode')
        seat_positions = data.get('seat_positions', [])
        quantity = data.get('quantity')
        section = data.get('section')
        subsection = data.get('subsection')

        Logger.base.info(
            f'📋 [SEAT_HANDLER] Processing BookingCreated - '
            f'booking: {booking_id}, buyer: {buyer_id}, event: {event_id}'
        )

        # 創建預訂請求
        reservation_request = ReservationRequest(
            booking_id=booking_id,
            buyer_id=buyer_id,
            event_id=event_id,
            selection_mode=seat_selection_mode,
            quantity=quantity,
            seat_positions=seat_positions,
            section_filter=section,
            subsection_filter=subsection,
        )

        # 執行座位預訂
        result = await self.reserve_use_case.reserve_seats(reservation_request)

        # 發送結果事件回 booking_service
        await self._send_reservation_result(result)

        return result.success

    async def _handle_seat_reservation_request(self, event_data: Dict[str, Any]) -> bool:
        """處理直接的座位預訂請求"""
        # 類似 _handle_booking_created 的邏輯
        Logger.base.info(
            f'🎯 [SEAT_HANDLER] Processing direct seat reservation request: {event_data.get("event_type", "Unknown")}'
        )
        # TODO: 實現直接預訂邏輯
        return True

    async def _handle_seat_release_request(self, event_data: Dict[str, Any]) -> bool:
        """處理座位釋放請求（取消/超時）"""
        data = event_data.get('data', {})

        booking_id = data.get('booking_id')
        # seat_ids = data.get("seat_ids", [])  # TODO: 實現座位釋放邏輯時使用

        Logger.base.info(f'🔓 [SEAT_HANDLER] Processing seat release for booking {booking_id}')

        # TODO: 實現座位釋放邏輯
        # 發送釋放命令到 RocksDB

        return True

    async def _send_reservation_result(self, result) -> None:
        """
        發送預訂結果回 booking_service
        """
        try:
            from datetime import datetime

            from src.seat_reservation.use_case.reserve_seats_use_case import SeatReservationResult
            from src.shared.message_queue.unified_mq_publisher import publish_domain_event

            if result.success:
                event_type = 'SeatReservationSuccess'
                Logger.base.info(
                    f'✅ [SEAT_HANDLER] Sending success result for booking {result.booking_id}'
                )
            else:
                event_type = 'SeatReservationFailed'
                Logger.base.warning(
                    f'❌ [SEAT_HANDLER] Sending failure result for booking {result.booking_id}: '
                    f'{result.error_message}'
                )

            # 創建結果事件
            result_event = SeatReservationResult(
                booking_id=result.booking_id,
                success=result.success,
                reserved_seats=result.reserved_seats or [],
                total_price=result.total_price,
                error_message=result.error_message or '',
                event_id=result.event_id or 0,
                occurred_at=datetime.now(),
            )

            # 發送事件到 booking service
            await publish_domain_event(
                event=result_event,
                topic='seat-reservation-results',
                partition_key=str(result.booking_id),
            )

            Logger.base.info(
                f'📤 [SEAT_HANDLER] Sent {event_type} event for booking {result.booking_id}'
            )

        except Exception as e:
            Logger.base.error(
                f'❌ [SEAT_HANDLER] Failed to send reservation result for booking {result.booking_id}: {e}'
            )

        # TODO: 發送事件到 Kafka
        # await publish_domain_event(
        #     event={
        #         "event_type": event_type,
        #         "data": asdict(result)
        #     },
        #     topic="seat-reservation-results",
        #     partition_key=str(result.booking_id)
        # )


class SeatReservationConsumer:
    """
    座位預訂消費者

    這是 seat_reservation 服務的主要入口點
    """

    def __init__(self):
        self.consumer = None
        self.handler = None
        self.running = False

    @Logger.io
    async def initialize(self):
        """初始化消費者和處理器"""
        # 創建處理器
        reserve_use_case = create_reserve_seats_use_case()
        self.handler = SeatReservationEventHandler(reserve_use_case)

        # 創建統一消費者
        topics = [
            'booking-events',  # 來自 booking_service
            'seat-reservation-requests',  # 直接預訂請求
        ]

        self.consumer = UnifiedEventConsumer(
            topics=topics,
            consumer_group_id='seat-reservation-service',
            consumer_tag='[SEAT_RESERVATION]',
        )

        # 註冊處理器
        self.consumer.register_handler(self.handler)

        Logger.base.info('🏗️ [SEAT_CONSUMER] Initialized seat reservation consumer')

    @Logger.io
    async def start(self):
        """啟動消費者"""
        if not self.consumer:
            await self.initialize()

        Logger.base.info('🚀 [SEAT_CONSUMER] Starting seat reservation consumer...')
        self.running = True

        try:
            if self.consumer is None:
                raise RuntimeError('Consumer not initialized')
            await self.consumer.start()
        except Exception as e:
            Logger.base.error(f'❌ [SEAT_CONSUMER] Error starting consumer: {e}')
            raise
        finally:
            self.running = False

    @Logger.io
    async def stop(self):
        """停止消費者"""
        if self.consumer and self.running:
            Logger.base.info('⏹️ [SEAT_CONSUMER] Stopping seat reservation consumer...')
            await self.consumer.stop()
            self.running = False


# 全局實例
_seat_reservation_consumer = None


async def get_seat_reservation_consumer() -> SeatReservationConsumer:
    """獲取座位預訂消費者實例"""
    global _seat_reservation_consumer

    if _seat_reservation_consumer is None:
        _seat_reservation_consumer = SeatReservationConsumer()
        await _seat_reservation_consumer.initialize()

    return _seat_reservation_consumer


# 啟動腳本
if __name__ == '__main__':

    async def main():
        consumer = await get_seat_reservation_consumer()
        await consumer.start()

    # 啟動消費者
    asyncio.run(main())
