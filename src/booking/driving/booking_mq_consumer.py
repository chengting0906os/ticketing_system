"""
Booking MQ Consumer - Order Status Manager
訂單 MQ 消費者 - 訂單狀態管理器

職責：
- 監聽來自 seat_reservation 的狀態更新事件
- 處理 pending_payment 和 failed 狀態更新
- 管理訂單生命週期

架構：
- 使用 Quix Streams 無狀態 consumer
- 直接處理 2 個 topics (pending_payment, failed)
- 透過 BookingMqGateway 處理業務邏輯
"""

import os
from typing import Optional

import anyio
from quixstreams import Application

from src.booking.driving.booking_mq_gateway import BookingMqGateway
from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.kafka_constant_builder import (
    KafkaConsumerGroupBuilder,
    KafkaTopicBuilder,
)


# Kafka 配置
KAFKA_COMMIT_INTERVAL = 0.5
KAFKA_RETRIES = 3


class BookingMqConsumer:
    """
    處理訂單狀態更新的 MQ 消費者

    與其他 consumer 一樣使用 Quix Streams，保持架構一致性
    """

    def __init__(self):
        self.kafka_app: Optional[Application] = None
        self.gateway: Optional[BookingMqGateway] = None
        self.running = False
        self.event_id = int(os.getenv('EVENT_ID', '1'))
        self.consumer_group_id = os.getenv(
            'CONSUMER_GROUP_ID', KafkaConsumerGroupBuilder.booking_service(event_id=self.event_id)
        )
        self.instance_id = os.getenv('CONSUMER_INSTANCE_ID', '1')

    def _create_kafka_app(self) -> Application:
        """
        創建 Kafka 應用 (無狀態)

        與 SeatReservation 類似，不需要 stateful processing
        """
        app = Application(
            broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=self.consumer_group_id,
            commit_interval=KAFKA_COMMIT_INTERVAL,
            producer_extra_config={
                'enable.idempotence': True,
                'acks': 'all',
                'retries': KAFKA_RETRIES,
            },
            consumer_extra_config={
                'enable.auto.commit': False,
                'auto.offset.reset': 'earliest',
            },
        )

        Logger.base.info('📚 [BOOKING] Created Kafka app (stateless)')
        Logger.base.info(f'👥 Consumer group: {self.consumer_group_id}')
        return app

    def _setup_kafka_processing(self):
        """設置 Kafka processing - 處理 2 個 status update topics"""
        if not self.kafka_app:
            self.kafka_app = self._create_kafka_app()

        # Topic 1: Pending Payment 狀態更新 (from seat_reservation)
        pending_payment_topic = self.kafka_app.topic(
            name=KafkaTopicBuilder.update_booking_status_to_pending_payment(event_id=self.event_id),
            key_serializer='str',
            value_serializer='json',
        )

        # Topic 2: Failed 狀態更新 (from seat_reservation)
        failed_topic = self.kafka_app.topic(
            name=KafkaTopicBuilder.update_booking_status_to_failed(event_id=self.event_id),
            key_serializer='str',
            value_serializer='json',
        )

        # 設置無狀態處理
        self.kafka_app.dataframe(topic=pending_payment_topic).apply(
            self._process_pending_payment, stateful=False
        )

        self.kafka_app.dataframe(topic=failed_topic).apply(self._process_failed, stateful=False)

        Logger.base.info('✅ [BOOKING] All 2 status update streams configured')

    @Logger.io
    def _process_pending_payment(self, message):
        """
        處理 pending_payment 狀態更新

        透過 gateway 處理業務邏輯
        """
        try:
            Logger.base.info(f'💰 [BOOKING] Processing pending_payment: {message}')

            # 使用 anyio 執行 async gateway
            result = anyio.from_thread.run(self.gateway.handle_event, event_data=message)

            Logger.base.info(f'✅ [BOOKING] Pending payment processed: {result}')
            return {'success': True, 'result': result}

        except Exception as e:
            Logger.base.error(f'❌ [BOOKING] Failed to process pending_payment: {e}')
            return {'success': False, 'error': str(e)}

    @Logger.io
    def _process_failed(self, message):
        """
        處理 failed 狀態更新

        透過 gateway 處理業務邏輯
        """
        try:
            Logger.base.info(f'❌ [BOOKING] Processing failed status: {message}')

            # 使用 anyio 執行 async gateway
            result = anyio.from_thread.run(self.gateway.handle_event, event_data=message)

            Logger.base.info(f'✅ [BOOKING] Failed status processed: {result}')
            return {'success': True, 'result': result}

        except Exception as e:
            Logger.base.error(f'❌ [BOOKING] Failed to process failed status: {e}')
            return {'success': False, 'error': str(e)}

    async def start(self):
        """啟動訂單狀態管理消費者"""
        try:
            # 創建 Gateway
            self.gateway = BookingMqGateway()

            # 設置 Kafka processing
            self._setup_kafka_processing()

            consumer_tag = f'[BOOKING-{self.instance_id}]'

            Logger.base.info(f'📚 {consumer_tag} Starting booking status manager')
            Logger.base.info(f'📊 Event ID: {self.event_id}, Group: {self.consumer_group_id}')

            self.running = True

            # 啟動 Kafka processing
            if self.kafka_app:
                self.kafka_app.run()

        except Exception as e:
            Logger.base.error(f'❌ Booking consumer failed: {e}')
            raise

    async def stop(self):
        """停止訂單狀態管理消費者"""
        if self.running:
            self.running = False

            if self.kafka_app:
                try:
                    Logger.base.info('🛑 Stopping Kafka application...')
                    self.kafka_app = None
                except Exception as e:
                    Logger.base.warning(f'⚠️ Error stopping Kafka app: {e}')

            Logger.base.info('🛑 Booking consumer stopped')


def main():
    """主函數"""
    consumer = BookingMqConsumer()
    try:
        anyio.run(consumer.start)
    except KeyboardInterrupt:
        Logger.base.info('⚠️ Received interrupt signal')
    except Exception as e:
        Logger.base.error(f'💥 Consumer error: {e}')


if __name__ == '__main__':
    main()
