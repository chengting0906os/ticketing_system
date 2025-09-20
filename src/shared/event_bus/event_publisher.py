"""
Event Publisher for Domain Events using Kafka
"""

from abc import ABC, abstractmethod
import asyncio
from datetime import datetime
import json
from typing import Dict, List, Optional, Protocol, runtime_checkable

from kafka import KafkaProducer
from kafka.errors import KafkaError
import msgpack

from src.shared.config.core_setting import settings
from src.shared.logging.loguru_io import Logger


@runtime_checkable
class DomainEvent(Protocol):
    """Protocol for domain events"""

    @property
    def aggregate_id(self) -> int: ...

    @property
    def occurred_at(self) -> datetime: ...


class EventPublisher(ABC):
    """Abstract base class for event publishers"""

    @abstractmethod
    async def publish(
        self, *, event: DomainEvent, topic: str, partition_key: Optional[str] = None
    ) -> None:
        """Publish a single event to a topic"""
        pass

    @abstractmethod
    async def publish_batch(
        self, *, events: List[DomainEvent], topic: str, partition_key: Optional[str] = None
    ) -> None:
        """Publish multiple events to a topic"""
        pass


class EventSerializer:
    """Handles serialization of domain events"""

    @staticmethod
    def _extract_event_attributes(event: DomainEvent) -> dict:
        """Extract all attributes from domain event, handling both regular and attrs classes"""
        # Try attrs.asdict() first as it's the most reliable for attrs classes
        try:
            import attrs

            return attrs.asdict(event)
        except ImportError:
            # attrs not available, fallback to dict methods
            pass
        except Exception:
            # Not an attrs instance or other attrs error, fallback to dict methods
            pass

        # Fallback to __dict__ for regular classes
        if hasattr(event, '__dict__'):
            return event.__dict__.copy()

        # Last resort: manual inspection using vars()
        try:
            return vars(event).copy()
        except TypeError:
            # Object doesn't have __dict__ and isn't an attrs instance
            return {}

    @staticmethod
    def _build_event_dict(event: DomainEvent, use_timestamp: bool = False) -> dict:
        """Build base event dictionary with consistent structure"""
        event_dict = {
            'event_type': event.__class__.__name__,
            'aggregate_id': event.aggregate_id,
            'occurred_at': event.occurred_at.timestamp()
            if use_timestamp
            else event.occurred_at.isoformat(),
            'data': {},
        }

        # Extract all attributes
        attributes = EventSerializer._extract_event_attributes(event)

        # Add non-core attributes to data section
        for key, value in attributes.items():
            if key not in ['aggregate_id', 'occurred_at']:
                if isinstance(value, datetime):
                    event_dict['data'][key] = (
                        value.timestamp() if use_timestamp else value.isoformat()
                    )
                else:
                    event_dict['data'][key] = value

        return event_dict

    @staticmethod
    def serialize_json(event: DomainEvent) -> bytes:
        """Serialize event to JSON bytes"""
        event_dict = EventSerializer._build_event_dict(event, use_timestamp=False)
        return json.dumps(event_dict).encode('utf-8')

    @staticmethod
    def serialize_msgpack(event: DomainEvent) -> bytes:
        """Serialize event to MessagePack bytes (more efficient)"""
        event_dict = EventSerializer._build_event_dict(event, use_timestamp=True)
        packed_data = msgpack.packb(event_dict)
        if not isinstance(packed_data, bytes):
            raise TypeError('MessagePack serialization did not return bytes')
        return packed_data


class KafkaEventPublisher(EventPublisher):
    """Kafka implementation of event publisher"""

    def __init__(self, use_msgpack: bool = True):
        """
        Initialize Kafka event publisher

        Args:
            use_msgpack: If True, use MessagePack serialization (more efficient)
                        If False, use JSON serialization (more readable)
        """
        self.use_msgpack = use_msgpack
        self.serializer = EventSerializer()
        self._producer: Optional[KafkaProducer] = None
        self._lock = asyncio.Lock()

    async def _get_producer(self) -> KafkaProducer:
        """Get or create Kafka producer (lazy initialization with error handling)"""
        if self._producer is None:
            async with self._lock:
                if self._producer is None:
                    try:
                        producer_config = getattr(settings, 'KAFKA_PRODUCER_CONFIG', {})
                        self._producer = KafkaProducer(
                            **producer_config,
                            value_serializer=None,  # We handle serialization ourselves
                            key_serializer=lambda x: str(x).encode('utf-8') if x else None,
                        )
                        Logger.base.info('Kafka producer initialized successfully')
                    except Exception as e:
                        Logger.base.error(f'Failed to initialize Kafka producer: {e}')
                        raise
        return self._producer

    async def publish(
        self, *, event: DomainEvent, topic: str, partition_key: Optional[str] = None
    ) -> None:
        """
        Publish a single event to Kafka topic

        Args:
            event: Domain event to publish
            topic: Kafka topic name
            partition_key: Optional custom partition key. If None, uses aggregate_id
        """
        producer = await self._get_producer()

        # Serialize event
        if self.use_msgpack:
            value = self.serializer.serialize_msgpack(event)
        else:
            value = self.serializer.serialize_json(event)

        # Use custom partition key or fall back to aggregate_id
        key = partition_key or str(event.aggregate_id)

        try:
            # Send to Kafka (async wrapper around sync producer)
            future = producer.send(
                topic=topic,
                value=value,
                key=key,
                headers=[
                    ('event_type', event.__class__.__name__.encode('utf-8')),
                    (
                        'content_type',
                        b'application/msgpack' if self.use_msgpack else b'application/json',
                    ),
                ],
            )

            # Wait for confirmation
            await asyncio.get_event_loop().run_in_executor(
                None,
                future.get,
                10,  # timeout in seconds
            )

            Logger.base.info(f'Published event {event.__class__.__name__} to {topic}')

        except KafkaError as e:
            Logger.base.error(f'Failed to publish event: {e}')
            raise

    async def publish_batch(
        self, *, events: List[DomainEvent], topic: str, partition_key: Optional[str] = None
    ) -> None:
        """
        Publish multiple events to Kafka topic

        Args:
            events: List of domain events to publish
            topic: Kafka topic name
            partition_key: Optional custom partition key. If None, uses aggregate_id for each event
        """
        if not events:
            return

        producer = await self._get_producer()
        futures = []

        for event in events:
            # Serialize event
            if self.use_msgpack:
                value = self.serializer.serialize_msgpack(event)
            else:
                value = self.serializer.serialize_json(event)

            # Use custom partition key or fall back to aggregate_id
            key = partition_key or str(event.aggregate_id)

            # Send to Kafka (collect futures)
            future = producer.send(
                topic=topic,
                value=value,
                key=key,
                headers=[
                    ('event_type', event.__class__.__name__.encode('utf-8')),
                    (
                        'content_type',
                        b'application/msgpack' if self.use_msgpack else b'application/json',
                    ),
                ],
            )
            futures.append(future)

        try:
            # Wait for all messages to be sent
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: [f.get(10) for f in futures]
            )

            Logger.base.info(f'Published {len(events)} events to {topic}')

        except KafkaError as e:
            Logger.base.error(f'Failed to publish batch: {e}')
            raise

    async def close(self):
        """Close the Kafka producer"""
        if self._producer:
            await asyncio.get_event_loop().run_in_executor(None, self._producer.close)
            self._producer = None


class InMemoryEventPublisher(EventPublisher):
    """In-memory implementation for testing"""

    def __init__(self):
        self.published_events: Dict[str, List[DomainEvent]] = {}

    async def publish(
        self, *, event: DomainEvent, topic: str, partition_key: Optional[str] = None
    ) -> None:
        """Store event in memory"""
        if topic not in self.published_events:
            self.published_events[topic] = []
        self.published_events[topic].append(event)
        Logger.base.debug(
            f'[TEST] Published event {event.__class__.__name__} to {topic} (key: {partition_key})'
        )

    async def publish_batch(
        self, *, events: List[DomainEvent], topic: str, partition_key: Optional[str] = None
    ) -> None:
        """Store events in memory"""
        if topic not in self.published_events:
            self.published_events[topic] = []
        self.published_events[topic].extend(events)
        Logger.base.debug(
            f'[TEST] Published {len(events)} events to {topic} (key: {partition_key})'
        )

    def get_events(self, *, topic: str) -> List[DomainEvent]:
        """Get all events for a topic (for testing)"""
        return self.published_events.get(topic, [])

    def clear(self):
        """Clear all events (for testing)"""
        self.published_events.clear()


class EventPublisherFactory:
    """Factory for creating event publisher instances"""

    @staticmethod
    def create_publisher(
        *, publisher_type: str = 'auto', use_msgpack: bool = True
    ) -> EventPublisher:
        """Create an event publisher instance

        Args:
            publisher_type: Type of publisher ("kafka", "memory", "auto")
            use_msgpack: Whether to use MessagePack serialization for Kafka

        Returns:
            EventPublisher instance
        """
        if publisher_type == 'auto':
            # Auto-detect based on environment
            if settings.DEBUG and not getattr(settings, 'KAFKA_BOOTSTRAP_SERVERS', None):
                return InMemoryEventPublisher()
            else:
                return KafkaEventPublisher(use_msgpack=use_msgpack)
        elif publisher_type == 'kafka':
            return KafkaEventPublisher(use_msgpack=use_msgpack)
        elif publisher_type == 'memory':
            return InMemoryEventPublisher()
        else:
            raise ValueError(f'Unknown publisher type: {publisher_type}')


# Global publisher instance (singleton)
_event_publisher: Optional[EventPublisher] = None


def get_event_publisher() -> EventPublisher:
    """Get the global event publisher instance"""
    global _event_publisher
    if _event_publisher is None:
        _event_publisher = EventPublisherFactory.create_publisher()
    return _event_publisher


def set_event_publisher(publisher: EventPublisher) -> None:
    """Set a custom event publisher (useful for testing)"""
    global _event_publisher
    _event_publisher = publisher


def reset_event_publisher() -> None:
    """Reset the global publisher instance (useful for testing)"""
    global _event_publisher
    if _event_publisher and hasattr(_event_publisher, 'close'):
        # Note: This is synchronous, consider making it async in the future
        pass  # For now, just reset the reference
    _event_publisher = None


def _generate_default_topic(event: DomainEvent) -> str:
    """Generate default topic name from event class name"""
    event_type = event.__class__.__name__.replace('Event', '').lower()
    return f'ticketing.{event_type}'


async def publish_domain_event(
    event: DomainEvent, topic: Optional[str] = None, partition_key: Optional[str] = None
) -> None:
    """
    Convenience function to publish a domain event

    Args:
        event: The domain event to publish
        topic: Optional topic name. If not provided, uses default topic pattern
        partition_key: Optional custom partition key. If None, uses aggregate_id
    """
    if topic is None:
        topic = _generate_default_topic(event)

    publisher = get_event_publisher()
    await publisher.publish(event=event, topic=topic, partition_key=partition_key)


async def publish_domain_events_batch(
    events: List[DomainEvent], topic: Optional[str] = None, partition_key: Optional[str] = None
) -> None:
    """
    Convenience function to publish multiple domain events as a batch

    Args:
        events: List of domain events to publish
        topic: Optional topic name. If not provided, uses default topic pattern from first event
        partition_key: Optional custom partition key. If None, uses aggregate_id for each event
    """
    if not events:
        return

    if topic is None:
        topic = _generate_default_topic(events[0])

    publisher = get_event_publisher()
    await publisher.publish_batch(events=events, topic=topic, partition_key=partition_key)
