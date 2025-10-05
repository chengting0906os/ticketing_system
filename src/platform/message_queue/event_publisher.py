"""
Domain Event Publisher
領域事件發布器

簡化版事件發布接口 - 直接使用 Quix Streams
"""

from typing import Literal

from quixstreams import Application

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger
from src.shared_kernel.domain.domain_event.mq_domain_event import MqDomainEvent


# 全域 Quix Application 實例
_quix_app: Application | None = None


def _get_quix_app() -> Application:
    """取得全域 Quix Application 實例"""
    global _quix_app
    if _quix_app is None:
        _quix_app = Application(
            broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
            producer_extra_config={
                'enable.idempotence': True,
                'acks': 'all',
                'retries': 3,
                'compression.type': 'snappy',
            },
        )
    return _quix_app


@Logger.io
async def publish_domain_event(
    event: MqDomainEvent,
    topic: str,
    partition_key: str,
) -> Literal[True]:
    """
    發布領域事件到 Kafka

    Args:
        event: 領域事件對象
        topic: Kafka topic 名稱
        partition_key: 分區鍵（確保相同實體的事件順序處理）

    Returns:
        True（永遠成功，失敗會拋出異常）

    範例:
        await publish_domain_event(
            event=BookingCreated(booking_id=123, ...),
            topic=KafkaTopicBuilder.ticket_reserving_request(...),
            partition_key="booking-123"
        )
    """
    app = _get_quix_app()

    # 創建 topic（Quix 會自動處理重複創建）
    kafka_topic = app.topic(
        name=topic,
        key_serializer='str',
        value_serializer='json',
    )

    # 準備事件數據
    event_data = {
        'event_type': event.__class__.__name__,
        'aggregate_id': str(event.aggregate_id),
        'occurred_at': int(event.occurred_at.timestamp()),
        **event.__dict__,
    }

    # 移除已包含的欄位
    event_data.pop('aggregate_id', None)
    event_data.pop('occurred_at', None)

    # 發布事件
    with app.get_producer() as producer:
        message = kafka_topic.serialize(
            key=partition_key,
            value=event_data,
        )

        producer.produce(
            topic=kafka_topic.name,
            key=message.key,
            value=message.value,
        )

        producer.flush(timeout=5.0)

    Logger.base.info(f'📤 Published {event.__class__.__name__} to {topic} (key: {partition_key})')

    return True
