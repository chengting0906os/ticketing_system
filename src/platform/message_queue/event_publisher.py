"""
Domain Event Publisher
領域事件發布器

簡化版事件發布接口 - 直接使用 Quix Streams
"""

from datetime import datetime
from typing import Any, Literal

import attrs
from opentelemetry import trace
from opentelemetry.propagate import inject
from quixstreams import Application

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger
from src.service.shared_kernel.domain.domain_event import MqDomainEvent


# 全域 Quix Application 實例
_quix_app: Application | None = None


def _serialize_value(inst: type, field: attrs.Attribute, value: Any) -> Any:
    """
    自定義序列化器 - 將 datetime 轉換為 timestamp

    用於 attrs.asdict 的 value_serializer 參數
    """
    if isinstance(value, datetime):
        return int(value.timestamp())
    return value


def _get_quix_app() -> Application:
    """取得全域 Quix Application 實例 - 支援 Exactly-Once 語義"""
    global _quix_app
    if _quix_app is None:
        # 產生唯一的事務 ID (用於 exactly-once)
        instance_id = settings.KAFKA_PRODUCER_INSTANCE_ID
        transactional_id = f'ticketing-producer-{instance_id}'

        _quix_app = Application(
            broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
            processing_guarantee='exactly-once',  # 🆕 啟用 exactly-once
            producer_extra_config={
                'enable.idempotence': True,
                'acks': 'all',
                'retries': 3,
                'compression.type': 'snappy',
                'transactional.id': transactional_id,  # 🆕 事務 ID
                'max.in.flight.requests.per.connection': 5,  # 🆕 exactly-once 優化
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

    # 準備事件數據 - 使用 attrs.asdict 並確保 datetime 轉換為 timestamp
    event_dict = attrs.asdict(event, value_serializer=_serialize_value)

    event_data = {
        'event_type': event.__class__.__name__,
        'aggregate_id': str(event.aggregate_id),
        'occurred_at': int(event.occurred_at.timestamp()),
        **event_dict,
    }

    # 移除已包含的欄位
    event_data.pop('aggregate_id', None)
    event_data.pop('occurred_at', None)

    # Inject trace context into Kafka headers for distributed tracing
    headers = {}
    inject(headers)  # Injects traceparent, tracestate into headers dict

    # Convert headers to Kafka format (list of tuples)
    kafka_headers = [
        (k, v.encode('utf-8') if isinstance(v, str) else v) for k, v in headers.items()
    ]

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
            headers=kafka_headers,  # Add trace context headers
        )

        producer.flush(timeout=5.0)

    current_span = trace.get_current_span()
    trace_id = format(current_span.get_span_context().trace_id, '032x') if current_span else 'none'
    Logger.base.info(
        f'📤 Published {event.__class__.__name__} to {topic} '
        f'(key: {partition_key}, trace_id: {trace_id})'
    )

    return True
