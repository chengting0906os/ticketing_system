"""
Domain Event Publisher

Simplified event publishing interface - using Quix Streams directly
"""

from datetime import datetime
from typing import Any, Literal

import attrs
from opentelemetry import trace
from quixstreams import Application
from uuid_utils import UUID

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger
from src.platform.observability.tracing import inject_trace_context
from src.service.shared_kernel.domain.domain_event import MqDomainEvent


# Global Quix Application instance
_quix_app: Application | None = None
_global_producer = None  # Global producer instance


def _get_global_producer():
    """Get global producer instance - avoid creating new producer on every publish"""
    global _global_producer
    if _global_producer is None:
        app = _get_quix_app()
        _global_producer = app.get_producer()
    return _global_producer


def _serialize_value(inst: type, field: attrs.Attribute, value: Any) -> Any:
    """
    Custom serializer - convert datetime and UUID to JSON-serializable types

    Used as value_serializer parameter for attrs.asdict

    Handles:
    - datetime -> Unix timestamp (int)
    - UUID -> str (includes UUID7)
    """
    if isinstance(value, datetime):
        return int(value.timestamp())
    if isinstance(value, UUID):
        return str(value)
    return value


def _get_quix_app() -> Application:
    """Get global Quix Application instance - supports Exactly-Once semantics"""
    global _quix_app
    if _quix_app is None:
        # Generate unique transaction ID (for exactly-once)
        instance_id = settings.KAFKA_PRODUCER_INSTANCE_ID
        transactional_id = f'ticketing-producer-{instance_id}'

        _quix_app = Application(
            broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
            processing_guarantee='exactly-once',  # Enable exactly-once
            producer_extra_config={
                'enable.idempotence': True,
                'acks': 'all',
                'retries': 3,
                'compression.type': 'snappy',
                'transactional.id': transactional_id,  # Transaction ID
                'max.in.flight.requests.per.connection': 5,  # Exactly-once optimization
                # Batching configuration for optimal throughput
                'linger.ms': 50,  # Wait up to 10ms to batch messages
                'batch.size': 32768,  # 32KB batch size (default: 16KB)
                'batch.num.messages': 1000,  # Max messages per batch
            },
        )
    return _quix_app


async def publish_domain_event(
    event: MqDomainEvent,
    topic: str,
    partition_key: str,
) -> Literal[True]:
    """
    Publish domain event to Kafka with distributed tracing support

    Args:
        event: Domain event object
        topic: Kafka topic name
        partition_key: Partition key (ensures ordered processing for same entity)

    Returns:
        True (always succeeds, failures raise exceptions)

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
            'event.aggregate_id': str(event.aggregate_id),
        },
    ):
        app = _get_quix_app()

        # Create topic (Quix automatically handles duplicate creation)
        kafka_topic = app.topic(
            name=topic,
            key_serializer='str',
            value_serializer='json',
        )

        # Prepare event data - use attrs.asdict and ensure datetime is converted to timestamp
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

        # Inject trace context into event data for distributed tracing
        trace_headers = inject_trace_context()
        event_data['_trace_headers'] = trace_headers

        # Publish event - use global producer instance
        producer = _get_global_producer()
        message = kafka_topic.serialize(
            key=partition_key,
            value=event_data,
        )

        producer.produce(
            topic=kafka_topic.name,
            key=message.key,
            value=message.value,
        )

        # No flush here - let Kafka batch messages automatically
        # Messages will be sent when batch.size or linger.ms threshold is reached
        # This significantly improves throughput for high-frequency events

        Logger.base.info(
            f'📤 Published {event.__class__.__name__} to {topic} (key: {partition_key})'
        )

        return True


def flush_all_messages(timeout: float = 10.0) -> int:
    """
    Flush all pending messages - call this before application shutdown

    Args:
        timeout: Maximum time to wait for flush (seconds)

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
