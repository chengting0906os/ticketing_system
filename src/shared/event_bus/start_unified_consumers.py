"""
統一的 Kafka 消費者啟動腳本
"""

import asyncio

from src.booking.infra.booking_event_handler import BookingEventHandler
from src.event_ticketing.infra.ticketing_event_handler import TicketingEventHandler
from src.shared.constant.topic import Topic
from src.shared.event_bus.event_consumer import start_unified_consumer
from src.shared.logging.loguru_io import Logger


async def main():
    """啟動統一的事件消費者"""
    Logger.base.info('Starting Unified Kafka Consumers Manager...')

    # 創建事件處理器
    booking_handler = BookingEventHandler()
    ticketing_handler = TicketingEventHandler()

    # 定義要監聽的topics
    topics = [
        Topic.TICKETING_BOOKING_REQUEST.value,  # ticketing-booking-request
        Topic.TICKETING_BOOKING_RESPONSE.value,  # ticketing-booking-response
    ]

    # 創建處理器列表
    handlers = [booking_handler, ticketing_handler]

    try:
        Logger.base.info('Starting unified event consumer...')

        # 啟動統一的消費者
        await start_unified_consumer(topics, handlers)

    except Exception as e:
        Logger.base.error(f'Failed to start unified consumer: {e}')
        raise


if __name__ == '__main__':
    asyncio.run(main())
