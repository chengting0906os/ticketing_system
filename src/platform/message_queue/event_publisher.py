"""
Domain Event Publisher

Simplified event publishing interface - using Quix Streams directly
Uses Protocol Buffers for efficient serialization
"""

from typing import Any, Literal

from opentelemetry import trace
from quixstreams import Application
from quixstreams.kafka import Producer
from quixstreams.models import Topic
from quixstreams.models.serializers.protobuf import ProtobufSerializer

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.protobuf_serializer import (
    convert_domain_event_to_proto,
    get_proto_class_by_event_type,
)
from src.platform.observability.tracing import inject_trace_context
from src.service.shared_kernel.domain.domain_event import MqDomainEvent


# Global Quix Application instance
_quix_app: Application | None = None
_global_producer = None  # Global producer instance
_quix_topic_object_cache: dict[str, Any] = {}  # Topic cache to avoid repeated list_topics calls
PROCESSING_GUARANTEE: Literal['at-least-once', 'exactly-once'] = 'at-least-once'


def _get_global_producer() -> Producer:
    """Get global producer instance - avoid creating new producer on every publish"""
    global _global_producer
    if _global_producer is None:
        app = _get_quix_app()
        _global_producer = app.get_producer()
    return _global_producer


def _get_quix_app() -> Application:
    """Get global Quix Application instance - supports At-Least-Once semantics"""
    global _quix_app
    if _quix_app is None:
        _quix_app = Application(
            broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
            processing_guarantee=PROCESSING_GUARANTEE,
            producer_extra_config={
                # === Idempotent Producer ===
                # Each message gets a sequence number (PID + seq),
                # broker tracks per-producer sequence, duplicates auto-discarded on retry
                'enable.idempotence': True,
                # acks=all: wait for all in-sync replicas to acknowledge (required for idempotence)
                'acks': 'all',
                # Retry up to 3 times on transient failures (network, leader election)
                'retries': 3,
                # === Batching & Compression (throughput optimization) ===
                # Snappy: fast compression, ~50% size reduction, low CPU overhead
                'compression.type': 'snappy',
                # Max concurrent requests per broker connection (5 is safe with idempotence)
                'max.in.flight.requests.per.connection': 5,
                # Wait up to 50ms to accumulate messages into batch (latency vs throughput tradeoff)
                'linger.ms': 50,
                # Max batch size in bytes (32KB, sends when reached even if linger.ms not elapsed)
                'batch.size': 32768,
                # Max messages per batch (sends when reached)
                'batch.num.messages': 500,
            },
        )
    return _quix_app


def _get_or_create_quix_topic_with_cache(topic_name: str, event_type: str) -> Topic:
    """
    Get cached topic object with native ProtobufSerializer.

    Performance optimization: app.topic() internally calls list_topics() which
    queries Kafka cluster metadata. Caching topics eliminates ~20% CPU overhead.

    Cache key includes event_type since each topic needs the correct protobuf serializer.
    """
    cache_key = f'{topic_name}:{event_type}'
    if cache_key not in _quix_topic_object_cache:
        app = _get_quix_app()
        proto_class = get_proto_class_by_event_type(event_type)
        _quix_topic_object_cache[cache_key] = app.topic(
            name=topic_name,
            key_serializer='str',
            value_serializer=ProtobufSerializer(msg_type=proto_class),
        )
    return _quix_topic_object_cache[cache_key]


async def publish_domain_event(
    event: MqDomainEvent,
    topic: str,
    partition_key: str,
) -> Literal[True]:
    """
    Example:
        await publish_domain_event(
            event=BookingCreated(booking_id=123, ...),
            topic=KafkaTopicBuilder.ticket_reserving_request(...),
            partition_key="booking-123"
        )
    """
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span(
        'kafka.publish',
        attributes={
            'messaging.system': 'kafka',
            'messaging.destination': topic,
            'messaging.destination_kind': 'topic',
            'messaging.kafka.partition_key': partition_key,
            'event.type': event.__class__.__name__,
        },
    ):
        # Get event type for protobuf serialization
        event_type = event.__class__.__name__
        kafka_topic = _get_or_create_quix_topic_with_cache(topic, event_type)
        trace_headers = inject_trace_context()
        proto_msg = convert_domain_event_to_proto(event, trace_context=trace_headers)
        producer = _get_global_producer()
        message = kafka_topic.serialize(
            key=partition_key,
            value=proto_msg,  # Pass protobuf message, serializer converts to bytes
        )

        producer.produce(
            topic=kafka_topic.name,
            key=message.key,
            value=message.value,
        )

        # No flush here - let Kafka batch messages automatically
        Logger.base.info(
            f'📤 Published {event.__class__.__name__} to {topic} (key: {partition_key})'
        )

        return True


def flush_all_messages(timeout: float = 10.0) -> int:
    """
    Returns:
        Number of messages still pending after timeout

    Example:
        # In FastAPI shutdown event
        @app.on_event("shutdown")
        async def shutdown_event():
            remaining = flush_all_messages(timeout=5.0)
            if remaining > 0:
                logger.warning(f"{remaining} messages not delivered")
    """
    producer = _get_global_producer()
    remaining = producer.flush(timeout=timeout)
    Logger.base.info(f'🔄 Flushed producer, {remaining} messages remaining')
    return remaining
