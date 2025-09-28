"""
Event Ticketing MQ Consumer
專門處理來自 Booking 服務的票務事件

職責：
- 監聽 ticketing-booking-request topic
- 處理 BookingCreated 事件
- 預訂票務並發送回應
"""

from typing import Optional
import uuid

import anyio

from src.event_ticketing.port.event_ticketing_mq_gateway import EventTicketingMqGateway
from src.event_ticketing.use_case.command.reserve_tickets_use_case import ReserveTicketsUseCase
from src.shared.config.db_setting import get_async_session
from src.shared.constant.topic import Topic
from src.shared.logging.loguru_io import Logger
from src.shared.message_queue.unified_mq_consumer import UnifiedEventConsumer
from src.shared.service.repo_di import get_ticket_command_repo, get_ticket_query_repo


class EventTicketingMqConsumer:
    """處理票務預訂事件的 MQ 消費者"""

    def __init__(self):
        self.consumer: Optional[UnifiedEventConsumer] = None
        self.session = None
        self.session_gen = None
        self.running = False

    async def start(self):
        """啟動消費者"""
        try:
            # 創建資料庫 session
            self.session_gen = get_async_session()
            self.session = await self.session_gen.__anext__()

            # 創建依賴項
            ticket_command_repo = get_ticket_command_repo(self.session)
            ticket_query_repo = get_ticket_query_repo(self.session)
            reserve_tickets_use_case = ReserveTicketsUseCase(
                self.session, ticket_command_repo, ticket_query_repo
            )
            event_ticketing_gateway = EventTicketingMqGateway(reserve_tickets_use_case)

            # 直接使用 Gateway 作為事件處理器
            ticketing_handler = event_ticketing_gateway

            # 定義要監聽的 topic - 只監聽請求
            topics = [Topic.TICKETING_BOOKING_REQUEST.value]

            # 創建消費者標籤
            consumer_id = str(uuid.uuid4())[:8]
            consumer_tag = f'[TICKETING-REQUEST-{consumer_id}]'

            Logger.base.info(f'🎫 {consumer_tag} 啟動票務請求消費者')
            Logger.base.info(f'📡 {consumer_tag} 監聽 topic: {topics}')

            # 創建統一消費者
            self.consumer = UnifiedEventConsumer(topics=topics, consumer_tag=consumer_tag)
            # 註冊處理器 - 使用 Gateway 對象
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

        # 清理資料庫 session
        if self.session:
            try:
                await self.session.close()
            except Exception as e:
                Logger.base.warning(f'⚠️ Session cleanup warning: {e}')
            self.session = None

        if self.session_gen:
            try:
                await self.session_gen.aclose()
            except Exception as e:
                Logger.base.warning(f'⚠️ Session generator cleanup warning: {e}')
            self.session_gen = None


async def main():
    """主函數"""
    consumer = EventTicketingMqConsumer()
    try:
        await consumer.start()
    except KeyboardInterrupt:
        Logger.base.info('⚠️ 收到中斷信號')
    except Exception as e:
        Logger.base.error(f'💥 消費者發生錯誤: {e}')
    finally:
        # 確保 consumer 總是被正確停止
        await consumer.stop()


if __name__ == '__main__':
    anyio.run(main)
