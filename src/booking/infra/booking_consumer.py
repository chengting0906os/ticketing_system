"""
Booking Kafka Consumer - 使用統一的 UnifiedEventConsumer 框架
"""

from typing import Optional

from src.booking.infra.booking_event_consumer import BookingEventConsumer
from src.shared.constant.topic import Topic
from src.shared.event_bus.event_consumer import UnifiedEventConsumer
from src.shared.logging.loguru_io import Logger


class BookingKafkaConsumer:
    """
    重構版本：使用統一的 UnifiedEventConsumer 框架

    【重構優勢】
    - 避免代碼重複，使用統一的消費框架
    - 業務邏輯集中在 BookingEventHandler
    - 更好的關注點分離
    - 更容易測試和維護
    """

    def __init__(self):
        self.unified_consumer: Optional[UnifiedEventConsumer] = None
        self.booking_handler = BookingEventConsumer()
        self.running = False

    async def start(self):
        """啟動統一的事件消費者"""
        try:
            # 使用統一的 UnifiedEventConsumer
            self.unified_consumer = UnifiedEventConsumer(
                topics=[Topic.TICKETING_BOOKING_RESPONSE],
                consumer_group_id='booking-service',
                consumer_tag='[BOOKING-CONSUMER]',
            )

            # 註冊 booking 事件處理器
            self.unified_consumer.register_handler(self.booking_handler)

            self.running = True
            Logger.base.info('Booking consumer started (using UnifiedEventConsumer)')

            # 啟動統一消費者
            await self.unified_consumer.start()

        except Exception as e:
            Logger.base.error(f'Failed to start booking consumer: {e}')
            raise

    @Logger.io
    async def stop(self):
        """停止 Consumer"""
        self.running = False
        if self.unified_consumer:
            await self.unified_consumer.stop()
        Logger.base.info('Booking consumer stopped')


# Global consumer instance
_booking_consumer = None


@Logger.io
async def start_booking_consumer():
    global _booking_consumer
    if _booking_consumer is None:
        _booking_consumer = BookingKafkaConsumer()
    await _booking_consumer.start()


@Logger.io
async def stop_booking_consumer():
    global _booking_consumer
    if _booking_consumer:
        await _booking_consumer.stop()
        _booking_consumer = None


@Logger.io
def get_booking_consumer() -> BookingKafkaConsumer:
    global _booking_consumer
    if _booking_consumer is None:
        _booking_consumer = BookingKafkaConsumer()
    return _booking_consumer
