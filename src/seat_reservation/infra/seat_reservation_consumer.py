"""
Seat Reservation Consumer - Seat Selection Router
座位預訂服務消費者 - 座位選擇路由器
負責座位選擇算法和服務間協調
"""

import asyncio
import os

from src.shared.config.di import container
from src.shared.logging.loguru_io import Logger
from src.shared.message_queue.kafka_constant_builder import (
    KafkaConsumerGroupBuilder,
    KafkaTopicBuilder,
)
from src.shared.message_queue.unified_mq_consumer import UnifiedEventConsumer


class SeatReservationEventHandler:
    """座位選擇事件處理器 - 專門處理票券預訂請求"""

    def __init__(self, gateway):
        self.gateway = gateway

    async def handle(self, event_data: dict):
        """處理票券預訂請求 - 透過 Gateway 調用業務邏輯"""
        await self.gateway.handle(event_data)


class SeatReservationConsumer:
    """
    座位預訂消費者 - 負責讀取座位狀態和處理預訂請求

    職責：
    - 讀取 RocksDB 座位狀態
    - 接收來自 booking 的預訂請求
    - 執行座位選擇算法
    - 發布預訂結果到 event_ticketing
    """

    def __init__(self):
        self.consumer = None
        self.handler = None
        self.rocksdb_app = None
        self.event_id = int(os.getenv('EVENT_ID', '1'))
        self.consumer_group_id = os.getenv(
            'CONSUMER_GROUP_ID',
            KafkaConsumerGroupBuilder.seat_reservation_service(event_id=self.event_id),
        )
        self.instance_id = os.getenv('CONSUMER_INSTANCE_ID', '1')

    def _create_rocksdb_app(self):
        """創建 RocksDB 應用來讀取座位狀態"""
        from quixstreams import Application
        from quixstreams.state.rocksdb import RocksDBOptions
        from src.shared.config.core_setting import settings

        # 使用與 EventTicketingMqConsumer 相同的狀態目錄
        state_dir = f'./rocksdb_state/event_ticketing_{self.event_id}_instance_{self.instance_id}'

        app = Application(
            broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=f'{self.consumer_group_id}_reader',  # 不同的 consumer group
            state_dir=state_dir,
            rocksdb_options=RocksDBOptions(
                open_max_retries=3,
                open_retry_backoff=1.0,
            ),
            use_changelog_topics=True,
            commit_interval=0.5,
            consumer_extra_config={
                'enable.auto.commit': False,
                'auto.offset.reset': 'earliest',
            },
        )

        Logger.base.info(f'🪑 [SEAT-READER] Created RocksDB reader: {state_dir}')
        return app

    def read_seat_states(self, seat_ids: list) -> dict:
        """讀取座位狀態 - 從 RocksDB 直接讀取"""
        if not self.rocksdb_app:
            return {}

        Logger.base.info(f'🔍 [SEAT-READER] Reading states for seats: {seat_ids}')

        # 設置 stateful processing 來讀取狀態
        topic = self.rocksdb_app.topic(
            name='dummy_topic_for_reading',  # 只是為了建立 dataframe
            key_serializer='str',
            value_serializer='json',
        )

        sdf = self.rocksdb_app.dataframe(topic=topic)
        seat_states = {}

        def _read_state_processor(message, state):
            """處理器：從 RocksDB 讀取座位狀態"""
            for seat_id in seat_ids:
                seat_data = state.get(seat_id)
                if seat_data:
                    seat_states[seat_id] = seat_data
                    Logger.base.info(f'✅ [SEAT-READER] Found seat {seat_id}: {seat_data}')
                else:
                    Logger.base.warning(f'⚠️ [SEAT-READER] Seat {seat_id} not found in RocksDB')
            return message

        sdf.apply(_read_state_processor, stateful=True)

        return seat_states

    async def initialize(self):
        """初始化座位選擇路由器和 RocksDB 讀取器"""
        # 創建 RocksDB 讀取器
        self.rocksdb_app = self._create_rocksdb_app()

        # 使用 DI 容器創建 Gateway 和相關依賴
        gateway = container.seat_reservation_gateway()
        self.handler = SeatReservationEventHandler(gateway)

        # 監聽來自 booking 的預訂請求
        topics = [KafkaTopicBuilder.ticket_reserve_request(event_id=self.event_id)]

        consumer_tag = f'[SEAT-ROUTER-{self.instance_id}]'

        self.consumer = UnifiedEventConsumer(
            topics=topics,
            consumer_group_id=self.consumer_group_id,
            consumer_tag=consumer_tag,
        )

        self.consumer.register_handler(self.handler)

        Logger.base.info(f'🪑 {consumer_tag} Initialized seat selection router with RocksDB reader')
        Logger.base.info(f'📊 Event ID: {self.event_id}, Group: {self.consumer_group_id}')

    async def start(self):
        if not self.consumer:
            await self.initialize()

        Logger.base.info('🚀 Starting seat reservation router...')
        await self.consumer.start()  # pyright: ignore[reportOptionalMemberAccess]

    async def stop(self):
        if self.consumer:
            await self.consumer.stop()
            Logger.base.info('🛑 Seat reservation router stopped')


def main():
    consumer = SeatReservationConsumer()
    try:
        asyncio.run(consumer.start())
    except KeyboardInterrupt:
        Logger.base.info('⚠️ Received interrupt signal')
    except Exception as e:
        Logger.base.error(f'💥 Consumer error: {e}')


if __name__ == '__main__':
    main()
