"""
Domain Event Publisher

High-performance event publishing using confluent-kafka directly.
Uses Protocol Buffers for efficient serialization.

Features:
- Global producer instance for connection reuse
- Idempotent producer with acks=all for reliability
- Batching with linger.ms=50 for throughput
- Snappy compression
"""

from typing import Literal

from confluent_kafka import Producer
from opentelemetry import trace

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.protobuf_serializer import convert_domain_event_to_proto
from src.platform.observability.tracing import inject_trace_context
from src.service.shared_kernel.domain.domain_event import MqDomainEvent


# Global producer instance
_global_producer: Producer | None = None


def _get_global_producer() -> Producer:
    """Get global producer instance - avoid creating new producer on every publish"""
    global _global_producer
    if _global_producer is None:
        _global_producer = Producer(
            {
                'bootstrap.servers': settings.KAFKA_BOOTSTRAP_SERVERS,
                # === Reliability Settings ===
                'enable.idempotence': True,  # Exactly-once semantics
                'acks': 'all',  # Wait for all replicas
                'retries': 3,
                # === Batching for Throughput ===
                'linger.ms': 50,  # Wait up to 50ms for batching
                'batch.size': 16384,  # 16KB batch
                # === Compression ===
                'compression.type': 'snappy',
                # === Connection ===
                'max.in.flight.requests.per.connection': 5,
            }
        )
    return _global_producer


def _delivery_callback(err, msg) -> None:  # noqa: ANN001
    """Callback for message delivery reports with latency tracking"""
    if err:
        Logger.base.error(f'Message delivery failed: {err}')
    else:
        # Calculate broker latency (time from produce() to broker ack)
        latency_ms = msg.latency() * 1000 if msg.latency() else 0
        if latency_ms > 50:  # Only log slow deliveries
            Logger.base.warning(
                f'[SLOW-PRODUCE] topic={msg.topic()} partition={msg.partition()} '
                f'latency={latency_ms:.1f}ms'
            )


async def publish_domain_event(
    event: MqDomainEvent,
    topic: str,
    partition_key: str,
    *,
    partition: int | None = None,
) -> Literal[True]:
    """
    Publish domain event to Kafka topic.

    Args:
        event: Domain event to publish
        topic: Kafka topic name
        partition_key: Key for message ordering (used if partition is None)
        partition: Explicit partition number (bypasses key hashing for even distribution)

    Example:
        # Let Kafka hash the key to determine partition
        await publish_domain_event(
            event=BookingCreated(...),
            topic="bookings",
            partition_key="booking-123"
        )

        # Explicitly specify partition for even distribution
        await publish_domain_event(
            event=ReservationRequest(...),
            topic="reservations",
            partition_key="event-1:A-5",
            partition=42  # Calculated partition number
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
            'messaging.kafka.partition': partition if partition is not None else -1,
            'event.type': event.__class__.__name__,
        },
    ):
        # Inject trace context into event
        trace_headers = inject_trace_context()
        proto_msg = convert_domain_event_to_proto(event, trace_context=trace_headers)

        # Serialize protobuf to bytes
        value_bytes = proto_msg.SerializeToString()
        key_bytes = partition_key.encode('utf-8')

        # Get producer and send
        producer = _get_global_producer()
        producer.produce(
            topic=topic,
            key=key_bytes,
            value=value_bytes,
            partition=partition if partition is not None else -1,  # -1 = use partitioner
            callback=_delivery_callback,
        )

        # Trigger delivery callbacks (non-blocking)
        producer.poll(0)

        log_partition = (
            f'partition={partition}' if partition is not None else f'key={partition_key}'
        )
        Logger.base.info(f'Published {event.__class__.__name__} to {topic} ({log_partition})')

        return True


def flush_all_messages(timeout: float = 10.0) -> int:
    """
    Flush all pending messages.

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
    Logger.base.info(f'Flushed producer, {remaining} messages remaining')
    return remaining
