"""
Domain Event Publisher

Simplified event publishing interface using Quix Streams directly.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import attrs
from opentelemetry import trace
from opentelemetry.propagate import inject
from quixstreams import Application

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.domain.domain_event import MqDomainEvent


# Global Quix Application instance
_quix_app: Application | None = None

# Global Kafka Producer instance (singleton for performance)
_kafka_producer = None


def _serialize_value(inst: type, field: attrs.Attribute, value: Any) -> Any:
    """
    Custom serializer - converts datetime to timestamp and UUID to string.

    Used as value_serializer parameter for attrs.asdict.
    """
    if isinstance(value, datetime):
        return int(value.timestamp())
    if isinstance(value, UUID):
        return str(value)
    return value


def _get_quix_app() -> Application:
    """Get global Quix Application instance with exactly-once semantics."""
    global _quix_app
    if _quix_app is None:
        # Generate unique transaction ID for exactly-once delivery
        instance_id = settings.KAFKA_PRODUCER_INSTANCE_ID
        transactional_id = f'ticketing-producer-{instance_id}'

        _quix_app = Application(
            broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
            processing_guarantee='exactly-once',
            producer_extra_config={
                # Reliability (exactly-once)
                'enable.idempotence': True,
                'acks': 'all',
                'retries': 3,
                'transactional.id': transactional_id,
                'max.in.flight.requests.per.connection': 5,
                # Batching (high throughput)
                'linger.ms': 50,  # Auto-flush after 50ms
                'batch.size': 524288,  # 512KB batch size
                'batch.num.messages': 1000,  # Or 1000 messages
                # Network optimization
                'compression.type': 'lz4',  # lz4 faster than snappy
                'socket.send.buffer.bytes': 1048576,  # 1MB send buffer
            },
        )
    return _quix_app


def _get_kafka_producer():
    """
    Get global Kafka Producer instance (singleton pattern).

    PERFORMANCE: Creating a new producer per request is expensive (100-500ms):
    - TCP handshake + TLS
    - Metadata fetch (brokers, partitions)
    - Authentication

    Reusing a single producer instance:
    - Amortizes connection overhead
    - Leverages internal connection pool
    - Enables efficient batching (linger.ms)
    - Thread-safe for concurrent use
    """
    global _kafka_producer
    if _kafka_producer is None:
        app = _get_quix_app()
        _kafka_producer = app.get_producer()
    return _kafka_producer


async def publish_domain_event(
    event: MqDomainEvent,
    topic: str,
    partition_key: str,
    *,
    force_flush: bool = False,
) -> Literal[True]:
    app = _get_quix_app()

    # Create topic (Quix handles duplicate creation automatically)
    kafka_topic = app.topic(
        name=topic,
        key_serializer='str',
        value_serializer='json',
    )

    event_dict = attrs.asdict(event, value_serializer=_serialize_value)

    event_data = {
        'event_type': event.__class__.__name__,
        'aggregate_id': str(event.aggregate_id),
        'occurred_at': int(event.occurred_at.timestamp()),
        **event_dict,
    }

    # Remove already included fields
    event_data.pop('aggregate_id', None)
    event_data.pop('occurred_at', None)

    # Inject trace context into Kafka headers for distributed tracing
    headers = {}
    inject(headers)  # Injects traceparent, tracestate into headers dict

    # Convert headers to Kafka format (list of tuples)
    kafka_headers = [
        (k, v.encode('utf-8') if isinstance(v, str) else v) for k, v in headers.items()
    ]

    # Serialize message
    message = kafka_topic.serialize(
        key=partition_key,
        value=event_data,
    )

    # Use singleton producer (no context manager needed - producer is long-lived)
    producer = _get_kafka_producer()
    producer.produce(
        topic=kafka_topic.name,
        key=message.key,
        value=message.value,
        headers=kafka_headers,  # Add trace context headers
    )

    # Only critical events need immediate flush (e.g., payment confirmation)
    # Normal events are auto-batched by linger.ms=50, no manual flush needed
    if force_flush:
        producer.flush(timeout=1.0)

    current_span = trace.get_current_span()
    trace_id = format(current_span.get_span_context().trace_id, '032x') if current_span else 'none'
    Logger.base.debug(
        f'📤 Published {event.__class__.__name__} to {topic} '
        f'(key: {partition_key}, trace_id: {trace_id})'
    )

    return True
