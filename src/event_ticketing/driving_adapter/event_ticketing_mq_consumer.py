"""
Event Ticketing MQ Consumer - Kvrocks State Manager
票務事件消費者 - Kvrocks 狀態管理器

職責：
- 管理 Kvrocks 票據狀態 (AVAILABLE, RESERVED, SOLD)
- 處理狀態轉換請求 (reserved, paid, available)
- 與 PostgreSQL 同步

監聽的 3 個 Topics:
1. update_ticket_status_to_reserved_in_postgresql (from seat_reservation)
2. update_ticket_status_to_paid_in_postgresql (from booking)
3. update_ticket_status_to_available_in_kvrocks (from booking)

狀態轉換規則:
- AVAILABLE → RESERVED: 預訂座位
- RESERVED → SOLD: 完成支付
- RESERVED → AVAILABLE: 超時釋放
"""

import os
from typing import Dict, Optional

import anyio
from quixstreams import Application
from quixstreams.state.rocksdb import RocksDBOptions

from src.platform.config.core_setting import settings
from src.platform.config.db_setting import get_async_session
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.kafka_constant_builder import (
    KafkaConsumerGroupBuilder,
    KafkaTopicBuilder,
)


# 狀態轉換配置
STATE_TRANSITION_RULES = {
    'RESERVED': {'allowed_from': ['AVAILABLE'], 'required_fields': ['booking_id', 'buyer_id']},
    'SOLD': {'allowed_from': ['RESERVED'], 'required_fields': []},
    'AVAILABLE': {'allowed_from': ['RESERVED'], 'required_fields': []},
}

# Kvrocks 配置
KVROCKS_OPEN_MAX_RETRIES = 3
KVROCKS_OPEN_RETRY_BACKOFF = 1.0
KAFKA_COMMIT_INTERVAL = 0.5


class EventTicketingMqConsumer:
    """處理票務狀態管理的 MQ 消費者 - Kvrocks Aggregate Root"""

    def __init__(self):
        self.kvrocks_app: Optional[Application] = None
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

    def _create_kvrocks_app(self) -> Application:
        """
        創建 Kvrocks Stateful Application

        使用 Quix Streams 的 stateful processing 來管理票據狀態
        每個 instance 有獨立的 state directory
        """
        state_dir = f'./kvrocks_state/event_ticketing_{self.event_id}_instance_{self.instance_id}'

        app = Application(
            broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=self.consumer_group_id,
            state_dir=state_dir,
            rocksdb_options=RocksDBOptions(
                open_max_retries=KVROCKS_OPEN_MAX_RETRIES,
                open_retry_backoff=KVROCKS_OPEN_RETRY_BACKOFF,
            ),
            use_changelog_topics=True,
            commit_interval=KAFKA_COMMIT_INTERVAL,
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

        Logger.base.info(f'🏗️ [KVROCKS] Created Kvrocks app: {state_dir}')
        return app

    def _setup_kvrocks_processing(self):
        """設置 Kvrocks stateful processing - 只處理 3 個狀態更新 topics"""
        if not self.kvrocks_app:
            self.kvrocks_app = self._create_kvrocks_app()

        # Topic 1: Reserved 狀態更新 (from seat_reservation)
        reserved_topic = self.kvrocks_app.topic(
            name=KafkaTopicBuilder.update_ticket_status_to_reserved_in_postgresql(
                event_id=self.event_id
            ),
            key_serializer='str',
            value_serializer='json',
        )

        # Topic 2: Paid 狀態更新 (from booking)
        paid_topic = self.kvrocks_app.topic(
            name=KafkaTopicBuilder.update_ticket_status_to_paid_in_postgresql(
                event_id=self.event_id
            ),
            key_serializer='str',
            value_serializer='json',
        )

        # Topic 3: Available 狀態更新 (from booking - timeout release)
        available_topic = self.kvrocks_app.topic(
            name=KafkaTopicBuilder.update_ticket_status_to_available_in_kvrocks(
                event_id=self.event_id
            ),
            key_serializer='str',
            value_serializer='json',
        )

        # 設置 stateful processing for each topic
        self.kvrocks_app.dataframe(topic=reserved_topic).apply(
            self._process_status_to_reserved, stateful=True
        )
        self.kvrocks_app.dataframe(topic=paid_topic).apply(
            self._process_status_to_paid, stateful=True
        )
        self.kvrocks_app.dataframe(topic=available_topic).apply(
            self._process_status_to_available, stateful=True
        )

        Logger.base.info('✅ [EVENT-TICKETING] All 3 status update streams configured')

    def _validate_state_transition(
        self, current_status: str, target_status: str, message: Dict
    ) -> tuple[bool, Optional[str]]:
        """
        驗證狀態轉換是否合法

        Returns:
            (is_valid, error_message)
        """
        if target_status not in STATE_TRANSITION_RULES:
            return False, f'Invalid target status: {target_status}'

        rule = STATE_TRANSITION_RULES[target_status]

        # 檢查當前狀態是否允許轉換
        if current_status not in rule['allowed_from']:
            return False, f'Cannot transition from {current_status} to {target_status}'

        # 檢查必要欄位
        for field in rule['required_fields']:
            if field not in message:
                return False, f'Missing required field: {field}'

        return True, None

    def _update_seat_state(self, seat_state: Dict, target_status: str, message: Dict) -> Dict:
        """
        更新座位狀態

        根據目標狀態更新不同的欄位
        """
        updates: Dict = {'status': target_status}

        if target_status == 'RESERVED':
            updates.update(
                {
                    'booking_id': message['booking_id'],
                    'buyer_id': message['buyer_id'],
                    'reserved_at': message.get('timestamp'),
                }
            )
        elif target_status == 'SOLD':
            updates['sold_at'] = message.get('timestamp')
        elif target_status == 'AVAILABLE':
            updates.update(
                {
                    'booking_id': None,
                    'buyer_id': None,
                    'reserved_at': None,
                }
            )

        seat_state.update(updates)
        return seat_state

    @Logger.io
    def _process_status_to_reserved(self, message, state):
        """處理狀態轉為 RESERVED (預訂)"""
        return self._process_status_change(message, state, 'RESERVED', '🔒')

    @Logger.io
    def _process_status_to_paid(self, message, state):
        """處理狀態轉為 SOLD (完成支付)"""
        return self._process_status_change(message, state, 'SOLD', '💰')

    @Logger.io
    def _process_status_to_available(self, message, state):
        """處理狀態轉為 AVAILABLE (超時釋放)"""
        return self._process_status_change(message, state, 'AVAILABLE', '🔓')

    def _process_status_change(self, message, state, target_status: str, emoji: str):
        """
        通用狀態變更處理邏輯

        Args:
            message: Kafka 訊息
            state: Kvrocks state store
            target_status: 目標狀態 ('RESERVED', 'SOLD', 'AVAILABLE')
            emoji: 日誌 emoji
        """
        seat_id = message.get('seat_id')
        if not seat_id:
            Logger.base.error('❌ [KVROCKS] Missing seat_id in message')
            return {'success': False, 'error': 'Missing seat_id'}

        seat_state = state.get(seat_id)
        if not seat_state:
            Logger.base.warning(f'⚠️ [KVROCKS] Seat {seat_id} not found in state')
            return {'success': False, 'error': 'Seat not found'}

        current_status = seat_state.get('status')

        # 驗證狀態轉換
        is_valid, error = self._validate_state_transition(current_status, target_status, message)
        if not is_valid:
            Logger.base.warning(f'⚠️ [KVROCKS] Invalid transition for {seat_id}: {error}')
            return {'success': False, 'error': error}

        # 更新狀態
        seat_state = self._update_seat_state(seat_state, target_status, message)
        state.set(seat_id, seat_state)

        Logger.base.info(f'{emoji} [KVROCKS] {seat_id}: {current_status} → {target_status}')
        return {'success': True, 'seat_id': seat_id, 'status': target_status}

    async def start(self):
        """啟動票務狀態管理消費者"""
        try:
            # 創建資料庫 session
            self.session_gen = get_async_session()
            self.session = await self.session_gen.__anext__()

            # 設置 Kvrocks stateful processing
            self._setup_kvrocks_processing()

            # 創建消費者標籤
            consumer_tag = f'[EVENT-TICKETING-{self.instance_id}]'

            Logger.base.info(f'🎫 {consumer_tag} Starting event ticketing state manager')
            Logger.base.info(f'📊 Event ID: {self.event_id}, Group: {self.consumer_group_id}')

            self.running = True

            # 啟動 Kvrocks stateful processing
            if self.kvrocks_app:
                self.kvrocks_app.run()

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
