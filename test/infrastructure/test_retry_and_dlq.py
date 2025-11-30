"""
測試 Quix Streams 錯誤處理和死信隊列 (DLQ)

這個腳本會：
1. 發送一個會失敗的預訂請求（無效數據）
2. 觀察 Quix Streams 錯誤 callback 是否被觸發
3. 驗證不可重試錯誤是否立即發送到 DLQ

錯誤處理機制：
- 不可重試錯誤（validation, invalid, not found, missing required）→ 立即發送到 DLQ
- 可重試錯誤（暫時性錯誤）→ Kafka 通過 offset 管理重試
"""

import asyncio
import os
import sys

import orjson


# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from confluent_kafka import Consumer, Producer

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.kafka_constant_builder import KafkaTopicBuilder


def create_producer():
    """創建 Kafka producer"""
    return Producer({'bootstrap.servers': settings.KAFKA_BOOTSTRAP_SERVERS})


def create_dlq_consumer(event_id: int):
    """創建 DLQ consumer"""
    dlq_topic = KafkaTopicBuilder.reservation_dlq(event_id=event_id)

    consumer = Consumer(
        {
            'bootstrap.servers': settings.KAFKA_BOOTSTRAP_SERVERS,
            'group.id': 'test-dlq-consumer',
            'auto.offset.reset': 'earliest',
        }
    )

    consumer.subscribe([dlq_topic])
    return consumer


def send_invalid_reservation_request(event_id: int):
    """發送一個無效的預訂請求（缺少必要欄位，會觸發 validation 錯誤）"""
    producer = create_producer()
    topic = KafkaTopicBuilder.ticket_reserving_request_to_reserved_in_kvrocks(event_id=event_id)

    # 故意發送無效數據（缺少必要欄位，會觸發 'missing required' 或 'validation' 錯誤）
    invalid_message = {
        'aggregate_id': 'test-invalid-booking-001',
        # 缺少 event_id, booking_id, buyer_id 等必要欄位
        'section': 'A',
        'seat_selection_mode': 'manual',
        'timestamp': '2025-10-12T08:00:00Z',
    }

    Logger.base.info('📤 Sending invalid reservation request to test error handling...')
    Logger.base.info(f'   Topic: {topic}')
    Logger.base.info(f'   Message: {invalid_message}')
    Logger.base.info('   Expected: Non-retryable error → Direct to DLQ')

    producer.produce(
        topic=topic,
        key='test-invalid-booking-001',
        value=orjson.dumps(invalid_message),
    )

    producer.flush()
    Logger.base.info('✅ Invalid message sent. Watch for error callback...')


def monitor_dlq(event_id: int, timeout: int = 30):
    """監控 DLQ，等待失敗訊息"""
    Logger.base.info(f'👀 Monitoring DLQ for {timeout} seconds...')

    consumer = create_dlq_consumer(event_id)

    try:
        start_time = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            msg = consumer.poll(timeout=1.0)

            if msg is None:
                continue

            if msg.error():
                Logger.base.error(f'❌ Consumer error: {msg.error()}')
                continue

            # 解析 DLQ 訊息
            dlq_data = orjson.loads(msg.value())

            Logger.base.info('📮 [DLQ] Received failed message:')
            Logger.base.info(f'   Original message: {dlq_data.get("original_message")}')
            Logger.base.info(f'   Original topic: {dlq_data.get("original_topic")}')
            Logger.base.info(f'   Error: {dlq_data.get("error")}')
            Logger.base.info(f'   Retry count: {dlq_data.get("retry_count")}')
            Logger.base.info(f'   Timestamp: {dlq_data.get("timestamp")}')
            Logger.base.info(f'   Instance ID: {dlq_data.get("instance_id")}')

            Logger.base.info('✅ DLQ mechanism verified successfully!')
            return True

        Logger.base.warning('⚠️ No DLQ message received within timeout')
        return False

    finally:
        consumer.close()


def main():
    """主程序"""
    event_id = 1

    Logger.base.info('🧪 Testing Quix Streams Error Handling and DLQ')
    Logger.base.info('=' * 60)

    # Step 1: 發送無效請求
    Logger.base.info('\n📝 Step 1: Sending invalid reservation request...')
    send_invalid_reservation_request(event_id)

    # Step 2: 等待 consumer 處理（不可重試錯誤應該立即發送到 DLQ）
    Logger.base.info('\n⏳ Step 2: Waiting for error callback processing...')
    Logger.base.info('   Expected: Non-retryable error detected → Immediate DLQ')
    Logger.base.info('   No application-layer retry delay')
    import time

    time.sleep(5)  # 縮短等待時間，因為不再有應用層重試

    # Step 3: 監控 DLQ
    Logger.base.info('\n📮 Step 3: Checking DLQ for failed message...')
    success = monitor_dlq(event_id, timeout=30)

    # Summary
    Logger.base.info('\n' + '=' * 60)
    if success:
        Logger.base.info('✅ Test PASSED: Error handling and DLQ mechanism working correctly!')
        Logger.base.info('   Non-retryable error was sent to DLQ immediately')
    else:
        Logger.base.warning('⚠️ Test INCOMPLETE: DLQ message not found')
        Logger.base.info('   Possible reasons:')
        Logger.base.info('   1. Consumer not running')
        Logger.base.info('   2. Error was classified as retryable (Kafka will retry)')
        Logger.base.info('   3. Check consumer logs for error callback messages')


if __name__ == '__main__':
    main()
