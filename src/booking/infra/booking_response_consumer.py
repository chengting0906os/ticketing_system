"""
Booking Response Consumer
專門處理來自 Ticketing 服務的回應

職責：
- 監聽 ticketing-booking-response topic
- 處理 TicketsReserved 和 TicketReservationFailed 事件
- 更新訂單狀態
"""

from typing import Optional
import uuid

import anyio

from src.booking.infra.booking_event_consumer import BookingEventConsumer
from src.shared.constant.topic import Topic
from src.shared.event_bus.event_consumer import UnifiedEventConsumer
from src.shared.logging.loguru_io import Logger


class BookingResponseConsumer:
    """處理票務回應的消費者"""

    def __init__(self):
        self.consumer: Optional[UnifiedEventConsumer] = None
        self.running = False

    async def start(self):
        """啟動消費者"""
        try:
            # 創建事件處理器
            booking_handler = BookingEventConsumer()

            # 定義要監聽的 topic - 只監聽回應
            topics = [Topic.TICKETING_BOOKING_RESPONSE.value]

            # 創建消費者標籤
            consumer_id = str(uuid.uuid4())[:8]
            consumer_tag = f'[BOOKING-RESPONSE-{consumer_id}]'

            Logger.base.info(f'📚 {consumer_tag} 啟動訂單回應消費者')
            Logger.base.info(f'📡 {consumer_tag} 監聽 topic: {topics}')

            # 創建統一消費者
            self.consumer = UnifiedEventConsumer(topics=topics, consumer_tag=consumer_tag)
            # 註冊處理器
            self.consumer.register_handler(booking_handler)

            self.running = True
            await self.consumer.start()

        except Exception as e:
            Logger.base.error(f'❌ 訂單回應消費者啟動失敗: {e}')
            raise

    async def stop(self):
        """停止消費者"""
        if self.consumer and self.running:
            await self.consumer.stop()
            self.running = False
            Logger.base.info('🛑 訂單回應消費者已停止')


async def main():
    """主函數"""
    consumer = BookingResponseConsumer()
    try:
        await consumer.start()
    except KeyboardInterrupt:
        Logger.base.info('⚠️ 收到中斷信號')
        await consumer.stop()
    except Exception as e:
        Logger.base.error(f'💥 消費者發生錯誤: {e}')
        await consumer.stop()


if __name__ == '__main__':
    anyio.run(main)
