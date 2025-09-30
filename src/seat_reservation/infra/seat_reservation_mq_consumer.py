"""
Seat Reservation Consumer - Seat Selection Router
座位預訂服務消費者 - 座位選擇路由器
負責座位選擇算法和服務間協調
"""

import asyncio
import json
import os

import rocksdb

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
    座位預訂消費者 - 負責管理座位狀態和處理預訂請求

    職責：
    - 管理 RocksDB 座位狀態 (初始化、讀取、更新)
    - 接收來自 booking 的預訂請求
    - 執行座位選擇算法
    - 發布預訂結果到 event_ticketing
    """

    def __init__(self):
        self.consumer = None
        self.handler = None
        self.rocksdb_app = None
        self.seat_init_processor = None
        self.event_id = int(os.getenv('EVENT_ID', '1'))
        self.consumer_group_id = os.getenv(
            'CONSUMER_GROUP_ID',
            KafkaConsumerGroupBuilder.seat_reservation_service(event_id=self.event_id),
        )
        self.instance_id = os.getenv('CONSUMER_INSTANCE_ID', '1')

    def _create_rocksdb_app(self):
        """創建 RocksDB 應用來管理座位狀態"""
        from quixstreams import Application
        from quixstreams.state.rocksdb import RocksDBOptions
        from src.shared.config.core_setting import settings

        # SeatReservationConsumer 負責管理 RocksDB 狀態
        state_dir = f'./rocksdb_state/seat_reservation_{self.event_id}_instance_{self.instance_id}'

        app = Application(
            broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=self.consumer_group_id,
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

        Logger.base.info(f'🪑 [SEAT-MANAGER] Created RocksDB state manager: {state_dir}')
        return app

    def _setup_seat_initialization_processor(self):
        """設置座位初始化處理器 - 監聽座位初始化命令並存儲到 RocksDB"""
        if not self.rocksdb_app:
            Logger.base.error('❌ [SEAT-INIT] RocksDB app not initialized')
            return

        try:
            # 創建座位初始化 topic
            seat_init_topic = self.rocksdb_app.topic(
                name=KafkaTopicBuilder.seat_initialization_command_in_rocksdb(
                    event_id=self.event_id
                ),
                key_serializer='str',
                value_serializer='json',
            )
            sdf = self.rocksdb_app.dataframe(topic=seat_init_topic)

            # 座位初始化處理器 - 使用 state.set() 存儲座位數據
            def process_seat_initialization(message, state):
                """處理座位初始化消息並存儲到 RocksDB 狀態"""
                try:
                    seat_data = message
                    seat_id = seat_data.get('seat_id')

                    if not seat_id:
                        Logger.base.warning(
                            '⚠️ [SEAT-INIT] Missing seat_id in initialization message'
                        )
                        return message

                    # 使用 state.set() 存儲座位數據到 RocksDB
                    state.set(seat_id, seat_data)

                    Logger.base.debug(
                        f'✅ [SEAT-INIT] Initialized seat {seat_id}: '
                        f'status={seat_data.get("status")}, price={seat_data.get("price")}'
                    )

                    return message

                except Exception as e:
                    Logger.base.error(f'❌ [SEAT-INIT] Failed to process seat initialization: {e}')
                    return message

            # 應用座位初始化處理器
            sdf.apply(process_seat_initialization, stateful=True)
            self.seat_init_processor = sdf

            Logger.base.info('🏗️ [SEAT-INIT] Seat initialization processor setup completed')

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-INIT] Failed to setup seat initialization processor: {e}')

    def read_seat_states(self, seat_ids: list) -> dict:
        """讀取座位狀態 - 直接訪問自己的 RocksDB"""
        Logger.base.info(f'🔍 [SEAT-READER] Reading states for {len(seat_ids)} seats')

        seat_states = {}

        try:
            # 讀取 seat_reservation 服務自己的 RocksDB
            state_dir = f'./rocksdb_state/seat_reservation_{self.event_id}_instance_{self.instance_id}/seat-reservation-service-{self.instance_id}/default/event-id-{self.event_id}______seat-initialization-command-in-rocksdb______event-ticketing-service___to___seat-reservation-service/0'

            db = rocksdb.DB(state_dir, rocksdb.Options(create_if_missing=False), read_only=True)

            # 讀取每個座位的狀態
            for seat_id in seat_ids:
                try:
                    value = db.get(seat_id.encode('utf-8'))
                    if value:
                        seat_data = json.loads(value.decode('utf-8'))
                        seat_states[seat_id] = seat_data
                        Logger.base.debug(
                            f'✅ [SEAT-READER] Found {seat_id}: status={seat_data.get("status")}'
                        )
                except Exception as e:
                    Logger.base.warning(f'⚠️ [SEAT-READER] Failed to read seat {seat_id}: {e}')

            db.close()
            Logger.base.info(
                f'📊 [SEAT-READER] Retrieved {len(seat_states)} seat states from own RocksDB'
            )
            return seat_states

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-READER] Failed to access RocksDB: {e}')
            return {}

    async def initialize(self):
        """初始化座位狀態管理器和預訂路由器"""
        # 創建 RocksDB 狀態管理器
        self.rocksdb_app = self._create_rocksdb_app()

        # 設置座位初始化處理器
        self._setup_seat_initialization_processor()

        # 使用 DI 容器創建 Gateway 和相關依賴
        gateway = container.seat_reservation_gateway()
        self.handler = SeatReservationEventHandler(gateway)

        # 監聽來自 booking 的預訂請求
        topics = [
            KafkaTopicBuilder.ticket_reserving_request_to_reserved_in_rocksdb(
                event_id=self.event_id
            )
        ]

        consumer_tag = f'[SEAT-MANAGER-{self.instance_id}]'

        self.consumer = UnifiedEventConsumer(
            topics=topics,
            consumer_group_id=self.consumer_group_id,
            consumer_tag=consumer_tag,
        )

        self.consumer.register_handler(self.handler)

        Logger.base.info(f'🪑 {consumer_tag} Initialized seat state manager with RocksDB')
        Logger.base.info(f'📊 Event ID: {self.event_id}, Group: {self.consumer_group_id}')

    async def start(self):
        if not self.consumer:
            await self.initialize()

        Logger.base.info('🚀 Starting seat reservation state manager...')

        # 啟動 RocksDB 處理器 - 必須在背景運行
        if self.rocksdb_app and self.seat_init_processor is not None:
            import threading

            def run_rocksdb_processor():
                """在背景執行 RocksDB 狀態處理"""
                try:
                    Logger.base.info('🏗️ [SEAT-MANAGER] Starting RocksDB processor thread')
                    self.rocksdb_app.run()
                except Exception as e:
                    Logger.base.error(f'❌ [SEAT-MANAGER] RocksDB processor failed: {e}')

            # 在背景線程運行 RocksDB processor
            rocksdb_thread = threading.Thread(target=run_rocksdb_processor, daemon=True)
            rocksdb_thread.start()
            Logger.base.info('✅ [SEAT-MANAGER] RocksDB processor started in background')

        await self.consumer.start()  # pyright: ignore[reportOptionalMemberAccess]  # pyright: ignore[reportOptionalMemberAccess]  # pyright: ignore[reportOptionalMemberAccess]

    async def stop(self):
        if self.consumer:
            await self.consumer.stop()
            Logger.base.info('🛑 Seat reservation state manager stopped')


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
