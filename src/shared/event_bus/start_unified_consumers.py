"""
統一的 Kafka 消費者啟動腳本
"""

import asyncio
import os
from uuid_v7.base import uuid7

from src.booking.infra.booking_event_handler import BookingEventHandler
from src.event_ticketing.infra.ticketing_event_handler import TicketingEventHandler
from src.shared.constant.topic import Topic
from src.shared.event_bus.event_consumer import start_unified_consumer
from src.shared.logging.loguru_io import Logger


async def main():
    """啟動統一的事件消費者"""
    # 生成消費者實例ID
    consumer_id = str(uuid7())[:8]  # 使用前8位作為簡短標識
    process_id = os.getpid()

    # 在日志中添加消費者標識
    consumer_tag = f'[CONSUMER-{consumer_id}|PID-{process_id}]'

    Logger.base.info(f'{consumer_tag} Starting Unified Kafka Consumers Manager...')
    print(f'\033[96m🚀 {consumer_tag} 啟動統一消費者管理器\033[0m')

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
        Logger.base.info(f'{consumer_tag} Starting unified event consumer...')
        print(f'\033[94m⚡ {consumer_tag} 準備監聽 topics: {topics}\033[0m')

        # 啟動統一的消費者
        await start_unified_consumer(topics, handlers, consumer_tag=consumer_tag)

    except Exception as e:
        Logger.base.error(f'{consumer_tag} Failed to start unified consumer: {e}')
        print(f'\033[91m❌ {consumer_tag} 消費者啟動失敗: {e}\033[0m')
        raise


if __name__ == '__main__':
    asyncio.run(main())
