"""
Seat Reservation Consumer - Seat Selection Router
座位預訂服務消費者 - 座位選擇路由器
負責座位選擇算法和服務間協調
"""

import asyncio
import os

from src.seat_reservation.use_case.reserve_seats_use_case import create_reserve_seats_use_case
from src.shared.logging.loguru_io import Logger
from src.shared.message_queue.kafka_constant_builder import (
    KafkaConsumerGroupBuilder,
    KafkaTopicBuilder,
)
from src.shared.message_queue.unified_mq_consumer import UnifiedEventConsumer


class SeatReservationEventHandler:
    """座位選擇事件處理器"""

    def __init__(self, reserve_use_case):
        self.reserve_use_case = reserve_use_case

    async def handle_event(self, event_type: str, event_data: dict):
        """處理預訂請求：執行座位選擇算法和協調邏輯"""
        if event_type == 'ticket_reserve_request':
            await self.reserve_use_case.handle_reservation_request(event_data)
        else:
            Logger.base.warning(f'Unknown event type: {event_type}')


class SeatReservationConsumer:
    """
    座位預訂消費者 - 座位選擇路由器

    職責：
    - 接收來自 booking 的預訂請求
    - 執行座位選擇算法 (best-available, manual)
    - 協調 event_ticketing 和 booking 服務
    """

    def __init__(self):
        self.consumer = None
        self.handler = None
        self.event_id = int(os.getenv('EVENT_ID', '1'))
        # 使用統一的 KafkaConsumerGroupBuilder 而非舊的命名方式
        self.consumer_group_id = os.getenv(
            'CONSUMER_GROUP_ID',
            KafkaConsumerGroupBuilder.seat_reservation_service(event_id=self.event_id),
        )
        self.instance_id = os.getenv('CONSUMER_INSTANCE_ID', '1')

    async def initialize(self):
        """初始化座位選擇路由器"""
        reserve_use_case = create_reserve_seats_use_case()
        self.handler = SeatReservationEventHandler(reserve_use_case)

        # 監聽來自 booking 的預訂請求
        topics = [KafkaTopicBuilder.ticket_reserve_request(event_id=self.event_id)]

        consumer_tag = f'[SEAT-ROUTER-{self.instance_id}]'

        self.consumer = UnifiedEventConsumer(
            topics=topics,
            consumer_group_id=self.consumer_group_id,
            consumer_tag=consumer_tag,
        )

        self.consumer.register_handler(self.handler)

        Logger.base.info(f'🪑 {consumer_tag} Initialized seat selection router')
        Logger.base.info(f'📊 Event ID: {self.event_id}, Group: {self.consumer_group_id}')

    async def start(self):
        """啟動座位選擇路由器"""
        if not self.consumer:
            await self.initialize()

        Logger.base.info('🚀 Starting seat reservation router...')
        await self.consumer.start()  # pyright: ignore[reportOptionalMemberAccess]

    async def stop(self):
        """停止座位選擇路由器"""
        if self.consumer:
            await self.consumer.stop()
            Logger.base.info('🛑 Seat reservation router stopped')


def main():
    """主函數"""
    consumer = SeatReservationConsumer()
    try:
        asyncio.run(consumer.start())
    except KeyboardInterrupt:
        Logger.base.info('⚠️ Received interrupt signal')
    except Exception as e:
        Logger.base.error(f'💥 Consumer error: {e}')


if __name__ == '__main__':
    main()
