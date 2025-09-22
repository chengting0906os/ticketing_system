import asyncio
import signal
import sys

from src.booking.infra.booking_consumer import start_booking_consumer, stop_booking_consumer
from src.event_ticketing.infra.ticketing_consumer import (
    start_ticketing_consumer,
    stop_ticketing_consumer,
)
from src.shared.logging.loguru_io import Logger


class ConsumerManager:
    def __init__(self):
        self.running = False
        self.tasks = []

    async def start_all(self):
        try:
            Logger.base.info('Starting all Kafka consumers...')

            # 啟動 Event-Ticketing Consumer
            ticketing_task = asyncio.create_task(
                start_ticketing_consumer(), name='ticketing-consumer'
            )
            self.tasks.append(ticketing_task)

            # 啟動 Booking Consumer
            booking_task = asyncio.create_task(start_booking_consumer(), name='booking-consumer')
            self.tasks.append(booking_task)

            self.running = True
            Logger.base.info('All Kafka consumers started successfully')

            # 等待所有任務完成或被中斷
            await asyncio.gather(*self.tasks, return_exceptions=True)

        except Exception as e:
            Logger.base.error(f'Error starting consumers: {e}')
            await self.stop_all()
            raise

    async def stop_all(self):
        if not self.running:
            return

        Logger.base.info('Stopping all Kafka consumers...')
        self.running = False

        # 取消所有任務
        for task in self.tasks:
            if not task.done():
                task.cancel()

        # 等待任務完成
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

        # 停止 consumers
        try:
            await stop_ticketing_consumer()
            await stop_booking_consumer()
        except Exception as e:
            Logger.base.error(f'Error stopping consumers: {e}')

        Logger.base.info('All Kafka consumers stopped')

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
