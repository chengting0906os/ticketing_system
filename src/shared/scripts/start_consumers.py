import asyncio
import signal
import sys

from src.booking.infra.booking_event_consumer import BookingEventConsumer
from src.event_ticketing.infra.ticketing_event_consumer import TicketingEventConsumer
from src.shared.constant.topic import Topic
from src.shared.event_bus.event_consumer import start_unified_consumer, stop_unified_consumer
from src.shared.logging.loguru_io import Logger


class ConsumerManager:
    def __init__(self):
        self.running = False

    async def start_all(self):
        try:
            Logger.base.info('Starting unified Kafka consumer...')

            # 創建事件處理器
            booking_handler = BookingEventConsumer()
            ticketing_handler = TicketingEventConsumer()

            # 定義要監聽的topics
            topics = [
                Topic.TICKETING_BOOKING_REQUEST.value,  # ticketing-booking-request
                Topic.TICKETING_BOOKING_RESPONSE.value,  # ticketing-booking-response
            ]

            # 創建處理器列表
            handlers = [booking_handler, ticketing_handler]

            self.running = True
            Logger.base.info('Unified Kafka consumer started successfully')

            # 啟動統一的消費者 (this will run indefinitely)
            await start_unified_consumer(topics, handlers)

        except Exception as e:
            Logger.base.error(f'Error starting unified consumer: {e}')
            await self.stop_all()
            raise

    async def stop_all(self):
        if not self.running:
            return

        Logger.base.info('Stopping unified Kafka consumer...')
        self.running = False

        # 停止統一消費者
        try:
            await stop_unified_consumer()
        except Exception as e:
            Logger.base.error(f'Error stopping unified consumer: {e}')

        Logger.base.info('Unified Kafka consumer stopped')

    def handle_signal(self, signum, _frame):
        """處理系統信號"""
        Logger.base.info(f'Received signal {signum}, shutting down...')
        asyncio.create_task(self.stop_all())


async def main():
    """主函數"""
    manager = ConsumerManager()

    # 設置信號處理
    signal.signal(signal.SIGINT, manager.handle_signal)
    signal.signal(signal.SIGTERM, manager.handle_signal)

    try:
        await manager.start_all()
    except KeyboardInterrupt:
        Logger.base.info('Received keyboard interrupt')
    except Exception as e:
        Logger.base.error(f'Unexpected error: {e}')
    finally:
        await manager.stop_all()


if __name__ == '__main__':
    Logger.base.info('Kafka Consumers Manager starting...')

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        Logger.base.info('Consumer manager stopped')
    except Exception as e:
        Logger.base.error(f'Consumer manager failed: {e}')
        sys.exit(1)
