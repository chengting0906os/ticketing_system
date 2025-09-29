"""
Booking MQ Consumer - Order Status Manager
訂單 MQ 消費者 - 訂單狀態管理器

職責：
- 監聽來自 seat_reservation 的狀態更新事件
- 處理 pending_payment 和 failed 狀態更新
- 管理訂單生命週期和 Redis TTL
"""

import asyncio
import os
from typing import Optional

import anyio

from src.booking.port.booking_mq_gateway import BookingMqGateway
from src.shared.logging.loguru_io import Logger
from src.shared.message_queue.kafka_constant_builder import (
    KafkaConsumerGroupBuilder,
    KafkaTopicBuilder,
)
from src.shared.message_queue.unified_mq_consumer import UnifiedEventConsumer


class BookingMqConsumer:
    """處理訂單狀態更新的 MQ 消費者"""

    def __init__(self):
        self.consumer: Optional[UnifiedEventConsumer] = None
        self.running = False
        self.event_id = int(os.getenv('EVENT_ID', '1'))
        # 使用統一的 KafkaConsumerGroupBuilder 而非舊的命名方式
        self.consumer_group_id = os.getenv(
            'CONSUMER_GROUP_ID', KafkaConsumerGroupBuilder.booking_service(event_id=self.event_id)
        )
        self.instance_id = os.getenv('CONSUMER_INSTANCE_ID', '1')

    async def start(self):
        """啟動訂單狀態管理消費者"""
        try:
            # 創建訂單狀態處理器
            booking_gateway = BookingMqGateway()

            # 監聽來自 seat_reservation 的狀態更新 topics
            topics = [
                KafkaTopicBuilder.update_booking_status_to_pending_payment(event_id=self.event_id),
                KafkaTopicBuilder.update_booking_status_to_failed(event_id=self.event_id),
            ]

            # 創建消費者標籤
            consumer_tag = f'[BOOKING-{self.instance_id}]'

            Logger.base.info(f'📚 {consumer_tag} Starting booking status manager')
            Logger.base.info(f'📊 Event ID: {self.event_id}, Group: {self.consumer_group_id}')
            Logger.base.info(f'📡 {consumer_tag} Listening topics: {topics}')

            # 創建統一消費者
            self.consumer = UnifiedEventConsumer(
                topics=topics,
                consumer_group_id=self.consumer_group_id,
                consumer_tag=consumer_tag,
            )

            # 註冊狀態更新處理器
            self.consumer.register_handler(booking_gateway)

            self.running = True

            Logger.base.info(f'🚀 {consumer_tag} Attempting to connect to Kafka...')
            Logger.base.info(f'🔍 {consumer_tag} Consumer state: {self.consumer is not None}')
            Logger.base.info(f'🔍 {consumer_tag} Topics: {topics}')
            Logger.base.info(f'🔍 {consumer_tag} Group ID: {self.consumer_group_id}')

            # 等待一下確保 Kafka 準備好
            await asyncio.sleep(1)

            try:
                Logger.base.info(f'🔗 {consumer_tag} Starting UnifiedEventConsumer...')
                await self.consumer.start()
                Logger.base.info(f'✅ {consumer_tag} Successfully connected to Kafka!')
            except Exception as kafka_error:
                Logger.base.error(f'💥 {consumer_tag} Kafka connection failed: {kafka_error}')
                Logger.base.error(f'💥 {consumer_tag} Error type: {type(kafka_error).__name__}')
                raise

        except Exception as e:
            Logger.base.error(f'❌ Booking consumer failed: {e}')
            # 記錄詳細錯誤但不拋出異常，讓系統繼續運行
            Logger.base.info('📋 Booking consumer will retry when topics become available')
            self.running = False
            # 不拋出異常，允許系統繼續運行其他消費者

    async def stop(self):
        """停止訂單狀態管理消費者"""
        if self.consumer and self.running:
            await self.consumer.stop()
            self.running = False
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
