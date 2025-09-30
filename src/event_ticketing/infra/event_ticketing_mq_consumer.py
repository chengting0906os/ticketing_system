"""
Event Ticketing MQ Consumer - RocksDB State Manager
票務事件消費者 - RocksDB 狀態管理器

職責：
- 管理 RocksDB 票據狀態 (AVAILABLE, RESERVED, SOLD)
- 處理座位初始化
- 處理狀態轉換請求
- 與 PostgreSQL 同步
"""

import os
from typing import Optional

import anyio
from quixstreams import Application
from quixstreams.state.rocksdb import RocksDBOptions

from src.shared.config.core_setting import settings
from src.shared.config.db_setting import get_async_session
from src.shared.logging.loguru_io import Logger
from src.shared.message_queue.kafka_constant_builder import (
    KafkaConsumerGroupBuilder,
    KafkaTopicBuilder,
)


class EventTicketingMqConsumer:
    """處理票務狀態管理的 MQ 消費者 - RocksDB Aggregate Root"""

    def __init__(self):
        self.rocksdb_app: Optional[Application] = None
        self.session = None
        self.session_gen = None
        self.running = False
        self.event_id = int(os.getenv('EVENT_ID', '1'))
        # 使用統一的 KafkaConsumerGroupBuilder 而非舊的命名方式
        self.consumer_group_id = os.getenv(
            'CONSUMER_GROUP_ID',
            KafkaConsumerGroupBuilder.event_ticketing_service(event_id=self.event_id),
        )
        self.instance_id = os.getenv('CONSUMER_INSTANCE_ID', '1')

    def _create_rocksdb_app(self) -> Application:
        state_dir = f'./rocksdb_state/event_ticketing_{self.event_id}_instance_{self.instance_id}'

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
            producer_extra_config={
                'enable.idempotence': True,
                'acks': 'all',
                'retries': 3,
            },
            consumer_extra_config={
                'enable.auto.commit': False,
                'auto.offset.reset': 'earliest',
            },
        )

        Logger.base.info(f'🏗️ [ROCKSDB] Created RocksDB app: {state_dir}')
        return app

    def _setup_rocksdb_processing(self):
        """設置 RocksDB stateful processing"""
        if not self.rocksdb_app:
            self.rocksdb_app = self._create_rocksdb_app()

        # 座位初始化 topic
        seat_init_topic = self.rocksdb_app.topic(
            name=KafkaTopicBuilder.seat_initialization_command_in_rocksdb(event_id=self.event_id),
            key_serializer='str',
            value_serializer='json',
        )

        # 狀態更新 topics
        reserved_topic = self.rocksdb_app.topic(
            name=KafkaTopicBuilder.update_ticket_status_to_reserved_in_postgresql(
                event_id=self.event_id
            ),
            key_serializer='str',
            value_serializer='json',
        )

        paid_topic = self.rocksdb_app.topic(
            name=KafkaTopicBuilder.update_ticket_status_to_paid_in_postgresql(
                event_id=self.event_id
            ),
            key_serializer='str',
            value_serializer='json',
        )

        available_topic = self.rocksdb_app.topic(
            name=KafkaTopicBuilder.update_ticket_status_to_available_in_rocksdb(
                event_id=self.event_id
            ),
            key_serializer='str',
            value_serializer='json',
        )

        # 設置 stateful processing
        sdf = self.rocksdb_app.dataframe(topic=seat_init_topic)
        sdf.apply(self._process_seat_initialization, stateful=True)

        self.rocksdb_app.dataframe(topic=reserved_topic).apply(
            self._process_status_to_reserved, stateful=True
        )
        self.rocksdb_app.dataframe(topic=paid_topic).apply(
            self._process_status_to_paid, stateful=True
        )
        self.rocksdb_app.dataframe(topic=available_topic).apply(
            self._process_status_to_available, stateful=True
        )

        # 加上列出所有座位的功能
        sdf.apply(self._list_event_seats, stateful=True)

    @Logger.io
    def _process_seat_initialization(self, message, state):
        """處理座位初始化 - RocksDB 狀態創建"""
        seat_id = message['seat_id']
        seat_state = {
            'seat_id': seat_id,
            'event_id': message['event_id'],
            'status': 'AVAILABLE',
            'price': message['price'],
            'initialized_at': message.get('timestamp'),
            'booking_id': None,
            'buyer_id': None,
            'reserved_at': None,
            'sold_at': None,
        }

        state.set(seat_id, seat_state)

        # state.get() 結果
        retrieved_data = state.get(seat_id)
        print(f'🎯 state.get("{seat_id}"): {retrieved_data}')

        Logger.base.info(f'✅ [ROCKSDB]state.get("{seat_id}"): {retrieved_data}')
        return {'success': True, 'seat_id': seat_id}

    def _list_event_seats(self, message, state):
        """列出所有 event-id=1 的座位"""
        # 只在特定座位時執行，避免重複
        if message.get('seat_id') == 'A-1-1-1':
            print('\n🎫 所有 event-id=1 座位:')

            # 檢查常見的座位模式
            for section in ['A', 'B', 'C']:
                for row in range(1, 6):  # 前5排
                    for seat in range(1, 6):  # 前5個座位
                        seat_id = f'{section}-1-{row}-{seat}'
                        seat_data = state.get(seat_id)
                        if seat_data:
                            print(f'  🎯 state.get("{seat_id}"): {seat_data}')

        return message

    @Logger.io
    def _process_status_to_reserved(self, message, state):
        """處理狀態轉為 RESERVED"""
        seat_id = message['seat_id']
        seat_state = state.get(seat_id)

        if seat_state and seat_state['status'] == 'AVAILABLE':
            seat_state.update(
                {
                    'status': 'RESERVED',
                    'booking_id': message['booking_id'],
                    'buyer_id': message['buyer_id'],
                    'reserved_at': message.get('timestamp'),
                }
            )
            state.set(seat_id, seat_state)
            Logger.base.info(f'🔒 [ROCKSDB] Reserved seat {seat_id}')
            return {'success': True, 'seat_id': seat_id}

        return {'success': False, 'error': 'Seat not available'}

    @Logger.io
    def _process_status_to_paid(self, message, state):
        """處理狀態轉為 SOLD"""
        seat_id = message['seat_id']
        seat_state = state.get(seat_id)

        if seat_state and seat_state['status'] == 'RESERVED':
            seat_state.update(
                {
                    'status': 'SOLD',
                    'sold_at': message.get('timestamp'),
                }
            )
            state.set(seat_id, seat_state)
            Logger.base.info(f'💰 [ROCKSDB] Sold seat {seat_id}')
            return {'success': True, 'seat_id': seat_id}

        return {'success': False, 'error': 'Seat not reserved'}

    @Logger.io
    def _process_status_to_available(self, message, state):
        """處理狀態轉為 AVAILABLE (超時釋放)"""
        seat_id = message['seat_id']
        seat_state = state.get(seat_id)

        if seat_state and seat_state['status'] == 'RESERVED':
            seat_state.update(
                {
                    'status': 'AVAILABLE',
                    'booking_id': None,
                    'buyer_id': None,
                    'reserved_at': None,
                }
            )
            state.set(seat_id, seat_state)
            Logger.base.info(f'🔓 [ROCKSDB] Released seat {seat_id}')
            return {'success': True, 'seat_id': seat_id}

        return {'success': False, 'error': 'Seat not reserved'}

    async def start(self):
        """啟動票務狀態管理消費者"""
        try:
            # 創建資料庫 session
            self.session_gen = get_async_session()
            self.session = await self.session_gen.__anext__()

            # 設置 RocksDB stateful processing
            self._setup_rocksdb_processing()

            # 創建消費者標籤
            consumer_tag = f'[EVENT-TICKETING-{self.instance_id}]'

            Logger.base.info(f'🎫 {consumer_tag} Starting event ticketing state manager')
            Logger.base.info(f'📊 Event ID: {self.event_id}, Group: {self.consumer_group_id}')

            self.running = True

            # 啟動 RocksDB stateful processing
            if self.rocksdb_app:
                self.rocksdb_app.run()

        except Exception as e:
            Logger.base.error(f'❌ Event ticketing consumer failed: {e}')
            raise

    async def stop(self):
        """停止消費者"""
        if self.running:
            self.running = False
            Logger.base.info('🛑 Event ticketing consumer stopped')

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


def main():
    """主函數"""
    consumer = EventTicketingMqConsumer()
    try:
        anyio.run(consumer.start)
    except KeyboardInterrupt:
        Logger.base.info('⚠️ Received interrupt signal')
    except Exception as e:
        Logger.base.error(f'💥 Consumer error: {e}')


if __name__ == '__main__':
    main()
