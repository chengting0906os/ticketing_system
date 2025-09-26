"""
Ticketing Request Consumer
專門處理來自 Booking 服務的票務請求

職責：
- 監聽 ticketing-booking-request topic
- 處理 BookingCreated 事件
- 預訂票務並發送回應
"""

from typing import Optional
import uuid

import anyio

from src.event_ticketing.infra.event_ticketing_event_consumer import EventTicketingEventConsumer
from src.event_ticketing.port.event_ticketing_mq_gateway import EventTicketingMqGateway
from src.event_ticketing.use_case.reserve_tickets_use_case import ReserveTicketsUseCase
from src.shared.config.db_setting import get_async_session
from src.shared.constant.topic import Topic
from src.shared.event_bus.event_consumer import UnifiedEventConsumer
from src.shared.logging.loguru_io import Logger
from src.shared.service.repo_di import get_ticket_repo


class TicketingRequestConsumer:
    """處理票務預訂請求的消費者"""

    def __init__(self):
        self.consumer: Optional[UnifiedEventConsumer] = None
        self.running = False

    async def start(self):
        """啟動消費者"""
        try:
            # 創建資料庫 session
            async_session_gen = get_async_session()
            session = await async_session_gen.__anext__()

            # 創建依賴項
            ticket_repo = get_ticket_repo(session)
            reserve_tickets_use_case = ReserveTicketsUseCase(session, ticket_repo)
            event_ticketing_gateway = EventTicketingMqGateway(reserve_tickets_use_case)

            # 創建事件處理器
            ticketing_handler = EventTicketingEventConsumer(event_ticketing_gateway)

            # 定義要監聽的 topic - 只監聽請求
            topics = [Topic.TICKETING_BOOKING_REQUEST.value]

            # 創建消費者標籤
            consumer_id = str(uuid.uuid4())[:8]
            consumer_tag = f'[TICKETING-REQUEST-{consumer_id}]'

            Logger.base.info(f'🎫 {consumer_tag} 啟動票務請求消費者')
            Logger.base.info(f'📡 {consumer_tag} 監聽 topic: {topics}')

            # 創建統一消費者
            self.consumer = UnifiedEventConsumer(topics=topics, consumer_tag=consumer_tag)
            # 註冊處理器
            self.consumer.register_handler(ticketing_handler)

            self.running = True
            await self.consumer.start()

        except Exception as e:
            Logger.base.error(f'❌ 票務請求消費者啟動失敗: {e}')
            raise

    async def stop(self):
        """停止消費者"""
        if self.consumer and self.running:
            await self.consumer.stop()
            self.running = False
            Logger.base.info('🛑 票務請求消費者已停止')


async def main():
    """主函數"""
    consumer = TicketingRequestConsumer()
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
