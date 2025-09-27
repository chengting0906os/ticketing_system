"""
統一的 Kafka 消費者啟動腳本
"""

import asyncio
import os

from uuid_v7.base import uuid7

from src.booking.infra.booking_event_consumer import BookingEventConsumer
from src.event_ticketing.infra.event_ticketing_event_consumer import EventTicketingEventConsumer
from src.event_ticketing.port.event_ticketing_mq_gateway import EventTicketingMqGateway
from src.event_ticketing.use_case.command.reserve_tickets_use_case import ReserveTicketsUseCase
from src.shared.config.db_setting import get_async_session
from src.shared.constant.topic import Topic
from src.shared.event_bus.event_consumer import start_unified_consumer
from src.shared.logging.loguru_io import Logger
from src.shared.service.repo_di import get_ticket_repo


async def main():
    """啟動統一的事件消費者"""
    # 生成消費者實例ID
    consumer_id = str(uuid7())[:8]  # 使用前8位作為簡短標識
    process_id = os.getpid()

    # 在日志中添加消費者標識
    consumer_tag = f'[CONSUMER-{consumer_id}|PID-{process_id}]'

    Logger.base.info(f'\033[96m🚀 {consumer_tag} 啟動統一消費者管理器\033[0m')

    # 創建資料庫 session
    async_session_gen = get_async_session()
    session = await async_session_gen.__anext__()

    # 創建依賴項
    ticket_repo = get_ticket_repo(session)
    reserve_tickets_use_case = ReserveTicketsUseCase(session, ticket_repo)
    event_ticketing_gateway = EventTicketingMqGateway(reserve_tickets_use_case)

    # 創建事件處理器
    booking_handler = BookingEventConsumer()
    ticketing_handler = EventTicketingEventConsumer(event_ticketing_gateway)

    Logger.base.info(f'📋 {consumer_tag} 創建處理器完成:')
    Logger.base.info(f'  - BookingEventConsumer: {type(booking_handler).__name__}')
    Logger.base.info(f'  - EventTicketingEventConsumer: {type(ticketing_handler).__name__}')

    # 定義要監聽的topics
    topics = [
        Topic.TICKETING_BOOKING_REQUEST.value,  # ticketing-booking-request
        Topic.TICKETING_BOOKING_RESPONSE.value,  # ticketing-booking-response
    ]

    # 創建處理器列表
    handlers = [booking_handler, ticketing_handler]

    try:
        Logger.base.info(f'\033[94m⚡ {consumer_tag} 準備監聽 topics: {topics}\033[0m')

        # 啟動統一的消費者
        await start_unified_consumer(topics, handlers, consumer_tag=consumer_tag)

    except Exception as e:
        Logger.base.error(f'\033[91m❌ {consumer_tag} 消費者啟動失敗: {e}\033[0m')
        raise


if __name__ == '__main__':
    asyncio.run(main())
