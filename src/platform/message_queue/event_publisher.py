"""
Domain Event Publisher

High-performance event publishing using confluent-kafka's experimental AsyncIO Producer.
Uses Protocol Buffers for efficient serialization.

Features:
- Global async producer instance for connection reuse
- Idempotent producer with acks=all for reliability
- Batching with linger.ms=50 for throughput
- Snappy compression
- True async - doesn't block event loop
"""

from typing import Literal

from confluent_kafka.experimental.aio import AIOProducer
from opentelemetry import trace

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.protobuf_serializer import convert_domain_event_to_proto
from src.platform.observability.tracing import inject_trace_context
from src.service.shared_kernel.domain.domain_event import MqDomainEvent


# Global async producer instance
_global_producer: AIOProducer | None = None


async def _get_global_producer() -> AIOProducer:
    """Get global async producer instance - avoid creating new producer on every publish"""
    global _global_producer
    if _global_producer is None:
        _global_producer = AIOProducer(
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


async def publish_domain_event(
    *,
    event: MqDomainEvent,
    topic: str,
    partition: int,
) -> Literal[True]:
    """
    Publish domain event to Kafka topic (async, non-blocking).

    Args:
        event: Domain event to publish
        topic: Kafka topic name
        partition: Partition number (must be >= 0)

    Example:
        await publish_domain_event(
            event=ReservationRequest(...),
            topic="reservations",
            partition=42,
        )
    """
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span(
        'kafka.publish',
        attributes={
            'messaging.system': 'kafka',
            'messaging.destination': topic,
            'messaging.destination_kind': 'topic',
            'messaging.kafka.partition': partition,
            'event.type': event.__class__.__name__,
        },
    ):
        # Inject trace context into event
        trace_headers = inject_trace_context()
        proto_msg = convert_domain_event_to_proto(event, trace_context=trace_headers)

        # Serialize protobuf to bytes
        value_bytes = proto_msg.SerializeToString()

        # Get async producer and send (fire-and-forget)
        producer = await _get_global_producer()
        # produce() returns a coroutine that yields a Future
        # We don't await the Future to keep it fire-and-forget
        await producer.produce(topic=topic, value=value_bytes, partition=partition)

        Logger.base.info(f'Published {event.__class__.__name__} to {topic} (partition={partition})')

        return True


async def flush_all_messages() -> None:
    global _global_producer
    if _global_producer is not None:
        await _global_producer.flush()
        Logger.base.info('Flushed async producer')


async def close_producer() -> None:
    global _global_producer
    if _global_producer is not None:
        await _global_producer.flush()
        await _global_producer.close()
        _global_producer = None
        Logger.base.info('Closed async producer')
