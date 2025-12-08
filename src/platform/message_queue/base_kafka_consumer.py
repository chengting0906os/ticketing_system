"""
Base Kafka Consumer using AIOConsumer (experimental)

Fully async consumer that runs in the same event loop as FastAPI.
Uses anyio.create_task_group for parallel message processing.

Key differences from sync version:
- No ThreadPoolExecutor needed (uses async tasks)
- No BlockingPortal needed (same event loop)
- Handlers must be async
"""

from abc import ABC, abstractmethod
import time
from typing import Any, Awaitable, Callable, Dict, Optional

import anyio
from anyio import CancelScope, create_task_group
from confluent_kafka import KafkaError, KafkaException, Message, TopicPartition
from confluent_kafka.experimental.aio import AIOConsumer, AIOProducer
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message as ProtoMessage
from opentelemetry import trace
import orjson

from src.platform.config.core_setting import KafkaConfig, settings
from src.platform.logging.loguru_io import Logger
from src.platform.observability.tracing import extract_trace_context


class BaseKafkaConsumer(ABC):
    """
    Async Kafka Consumer base class.

    Tuning Parameters (subclasses can override):

    POLL_TIMEOUT_SECONDS: Max time poll() waits for messages
      - Default: 0.1s (100ms)
      - Too long → high latency; Too short → CPU spin

    COMMIT_INTERVAL_SECONDS: How often to batch commit offsets
      - Default: 0.5s (500ms)
      - Too long → more reprocessing on restart; Too short → broker overhead

    MAX_CONCURRENT_TASKS: Max concurrent message processing tasks
      - Default: 10
      - Adjust based on CPU cores and IO intensity

    MAX_PENDING_COMMITS: Force commit after this many messages
      - Default: 100
      - Works with COMMIT_INTERVAL_SECONDS to control commit frequency
    """

    POLL_TIMEOUT_SECONDS: float = 0.1
    COMMIT_INTERVAL_SECONDS: float = 0.5
    MAX_CONCURRENT_TASKS: int = 1
    MAX_PENDING_COMMITS: int = 100

    def __init__(
        self,
        *,
        service_name: str,
        event_id: int,
        consumer_group_id: str,
        dlq_topic: str,
    ) -> None:
        self.service_name = service_name
        self.event_id = event_id
        self.consumer_group_id = consumer_group_id
        self.dlq_topic = dlq_topic
        self.instance_id = settings.KAFKA_CONSUMER_INSTANCE_ID
        self.kafka_config = KafkaConfig(event_id=event_id, service=service_name)

        # Kafka clients (async)
        self.consumer: Optional[AIOConsumer] = None
        self.producer: Optional[AIOProducer] = None  # For sending to DLQ
        self.tracer = trace.get_tracer(__name__)

        # Running state control
        self.running = False
        self._cancel_scope: Optional[CancelScope] = None

        # Offset tracking (for batch commit)
        # Structure: { topic_name: { partition_id: next_offset_to_commit } }
        self._pending_offsets: Dict[str, Dict[int, int]] = {}
        self._pending_count = 0  # Messages pending commit
        self._last_commit_time = time.monotonic()

        # Semaphore to limit concurrent tasks
        self._semaphore: Optional[anyio.Semaphore] = None

    @abstractmethod
    def _get_topic_handlers(
        self,
    ) -> Dict[str, tuple[type, Callable[[Dict], Awaitable[Any]]]]:
        """
        Return topic name to async handler mapping.

        Returns:
            {
                'topic-name': (ProtobufClass, async_handler_function),
                ...
            }

        Example:
            return {
                'booking-created': (pb.BookingCreatedEvent, self._handle_booking_created),
                'booking-cancelled': (pb.BookingCancelledEvent, self._handle_cancelled),
            }

        Note: Handlers MUST be async functions.
        """
        pass

    @abstractmethod
    async def _initialize_dependencies(self) -> None:
        """Initialize use cases and dependencies before consumer starts."""
        pass

    def _create_consumer(self) -> AIOConsumer:
        """
        Create async Kafka Consumer with optimized settings.

        Key settings explained:
        - group.id: Consumer group name, consumers in same group share topic
        - auto.offset.reset: Where to start when no committed offset (earliest/latest)
        - enable.auto.commit: False = manual commit control
        - fetch.wait.max.ms: Max time broker waits for data (lower = lower latency)
        - session.timeout.ms: How long before consumer is considered dead
        """
        base_config = {
            'bootstrap.servers': settings.KAFKA_BOOTSTRAP_SERVERS,
            'group.id': self.consumer_group_id,
            'auto.offset.reset': settings.KAFKA_CONSUMER_AUTO_OFFSET_RESET,
            'enable.auto.commit': False,  # Manual commit for precise control
            # Low latency settings (librdkafka default: 500, 1)
            'fetch.wait.max.ms': 50,
            'fetch.min.bytes': 1,
            # Session management (librdkafka default: 45000, 3000)
            'session.timeout.ms': 45000,
            'heartbeat.interval.ms': 15000,
            # Reconnection (librdkafka default: 100, 10000)
            'reconnect.backoff.ms': 1000,
            'reconnect.backoff.max.ms': 30000,
        }

        # Merge extra config
        extra_config = self.kafka_config.consumer_config
        for key, value in extra_config.items():
            base_config[key] = value

        return AIOConsumer(base_config)

    def _create_producer(self) -> AIOProducer:
        """Create async producer for DLQ."""
        return AIOProducer(
            {
                'bootstrap.servers': settings.KAFKA_BOOTSTRAP_SERVERS,
                'acks': 'all',
                'retries': 3,
            }
        )

    def _deserialize_protobuf(self, msg: Message, proto_class: type) -> Dict:
        proto_msg: ProtoMessage = proto_class()
        proto_msg.ParseFromString(msg.value())
        return MessageToDict(proto_msg, preserving_proto_field_name=True)

    async def _send_to_dlq(
        self,
        *,
        message: Dict,
        original_topic: str,
        error: str,
        retry_count: int = 0,
    ) -> None:
        """Send failed message to Dead Letter Queue (async)."""
        if not self.producer:
            Logger.base.error('DLQ producer not initialized')
            return

        try:
            dlq_message = {
                'original_message': message,
                'original_topic': original_topic,
                'error': error,
                'retry_count': retry_count,
                'timestamp': time.time(),
                'instance_id': self.instance_id,
            }

            await self.producer.produce(
                topic=self.dlq_topic,
                key=str(message.get('booking_id', 'unknown')).encode('utf-8'),
                value=orjson.dumps(dlq_message),
            )

            Logger.base.warning(f'[DLQ] Sent: {message.get("booking_id")} - {error}')

        except Exception as e:
            Logger.base.error(f'[DLQ] Failed to send: {e}')

    def _track_offset(self, msg: Message) -> None:
        """
        Track processed offset for batch commit.

        Why +1? Kafka commits the NEXT offset to read, not the one just processed.
        Example: processed offset=5 → commit offset=6
        """
        topic, partition = msg.topic(), msg.partition()
        offset = msg.offset() + 1

        if topic not in self._pending_offsets:
            self._pending_offsets[topic] = {}

        if offset > self._pending_offsets[topic].get(partition, -1):
            self._pending_offsets[topic][partition] = offset
            self._pending_count += 1

    async def _maybe_commit_offsets(self, *, force: bool = False) -> None:
        """
        Batch commit offsets (async).

        Why batch? Committing every message = network round-trip overhead.
        Batch commit reduces broker load.

        Triggers when ANY of:
        - force=True (shutdown)
        - pending_count >= MAX_PENDING_COMMITS
        - time >= COMMIT_INTERVAL_SECONDS
        """
        now = time.monotonic()
        time_elapsed = now - self._last_commit_time

        should_commit = (
            force
            or self._pending_count >= self.MAX_PENDING_COMMITS
            or time_elapsed >= self.COMMIT_INTERVAL_SECONDS
        )

        if not should_commit or not self._pending_offsets:
            return

        try:
            offsets_to_commit = [
                TopicPartition(topic, partition, offset)
                for topic, partitions in self._pending_offsets.items()
                for partition, offset in partitions.items()
            ]

            if offsets_to_commit and self.consumer:
                await self.consumer.commit(offsets=offsets_to_commit, asynchronous=False)
                Logger.base.debug(f'[{self.service_name}] Committed {self._pending_count} offsets')

            self._pending_offsets.clear()
            self._pending_count = 0
            self._last_commit_time = now

        except Exception as e:
            Logger.base.error(f'[{self.service_name}] Commit failed: {e}')

    async def _process_message(
        self,
        msg: Message,
        proto_class: type,
        handler: Callable[[Dict], Awaitable[Any]],
        topic: str,
    ) -> None:
        """
        Process message asynchronously.

        Flow: deserialize → extract trace → call async handler → track offset
        On error → send to DLQ
        """
        try:
            data = self._deserialize_protobuf(msg, proto_class)

            extract_trace_context(
                headers={
                    'traceparent': data.get('traceparent', ''),
                    'tracestate': data.get('tracestate', ''),
                }
            )

            with self.tracer.start_as_current_span(
                f'consumer.{topic}',
                attributes={
                    'messaging.system': 'kafka',
                    'messaging.destination': topic,
                    'booking.id': data.get('booking_id', 'unknown'),
                },
            ):
                await handler(data)  # Async handler
                self._track_offset(msg)

        except Exception as e:
            Logger.base.error(f'[{self.service_name}] Error: {e}')

            try:
                data = self._deserialize_protobuf(msg, proto_class)
            except Exception:
                data = {'raw': msg.value().hex() if msg.value() else 'empty'}

            await self._send_to_dlq(message=data, original_topic=topic, error=str(e))
            self._track_offset(msg)  # Still track to avoid reprocessing

    async def _process_with_semaphore(
        self,
        msg: Message,
        proto_class: type,
        handler: Callable[[Dict], Awaitable[Any]],
        topic: str,
    ) -> None:
        """Process message with semaphore-limited concurrency."""
        assert self._semaphore is not None
        async with self._semaphore:
            await self._process_message(msg, proto_class, handler, topic)

    async def start(self) -> None:
        """Start async consumer with retry for topic creation."""
        max_retries, delay = 5, 2

        for attempt in range(1, max_retries + 1):
            try:
                await self._initialize_dependencies()

                handlers = self._get_topic_handlers()
                topics = list(handlers.keys())

                self.consumer = self._create_consumer()
                self.producer = self._create_producer()
                self._semaphore = anyio.Semaphore(self.MAX_CONCURRENT_TASKS)

                await self.consumer.subscribe(topics)

                Logger.base.info(
                    f'[{self.service_name}] Started async consumer: '
                    f'event={self.event_id} group={self.consumer_group_id} '
                    f'topics={topics} max_tasks={self.MAX_CONCURRENT_TASKS}'
                )

                self.running = True
                await self._run_loop(handlers)
                break

            except KafkaException as e:
                if 'UNKNOWN_TOPIC_OR_PART' in str(e) and attempt < max_retries:
                    Logger.base.warning(
                        f'[{self.service_name}] {attempt}/{max_retries}: Topic not ready, retry in {delay}s'
                    )
                    await anyio.sleep(delay)
                    delay *= 2
                else:
                    Logger.base.error(f'[{self.service_name}] Start failed: {e}')
                    raise

    async def _run_loop(
        self, handlers: Dict[str, tuple[type, Callable[[Dict], Awaitable[Any]]]]
    ) -> None:
        """
        Main async consumer loop.

        1. poll() fetches next message (async, max POLL_TIMEOUT_SECONDS)
        2. No message → check if commit needed
        3. Has message → spawn task for parallel processing (limited by semaphore)
        """
        async with create_task_group() as tg:
            self._cancel_scope = tg.cancel_scope

            while self.running:
                try:
                    msg = await self.consumer.poll(timeout=self.POLL_TIMEOUT_SECONDS)

                    if msg is None:
                        await self._maybe_commit_offsets()
                        continue

                    if msg.error():
                        if msg.error().code() != KafkaError._PARTITION_EOF:
                            Logger.base.error(f'[{self.service_name}] Kafka error: {msg.error()}')
                        continue

                    topic = msg.topic()
                    if topic not in handlers:
                        continue

                    proto_class, handler = handlers[topic]

                    # Spawn task with semaphore to limit concurrency
                    tg.start_soon(self._process_with_semaphore, msg, proto_class, handler, topic)

                    await self._maybe_commit_offsets()

                except Exception as e:
                    if not self.running:
                        break
                    Logger.base.error(f'[{self.service_name}] Loop error: {e}')
                    await anyio.sleep(0.1)

    async def stop(self) -> None:
        """
        Graceful async shutdown.

        Steps:
        1. Set stop flag
        2. Cancel task group (waits for in-flight tasks)
        3. Final offset commit
        4. Close Kafka consumer
        5. Close DLQ producer
        """
        if not self.running:
            return

        Logger.base.info(f'[{self.service_name}] Stopping async consumer...')

        self.running = False

        # Cancel task group to stop accepting new tasks
        if self._cancel_scope:
            self._cancel_scope.cancel()

        # Final commit
        await self._maybe_commit_offsets(force=True)

        # Close consumer
        if self.consumer:
            try:
                await self.consumer.close()
            except Exception as e:
                Logger.base.warning(f'[{self.service_name}] Close error: {e}')

        # Close DLQ producer
        if self.producer:
            await self.producer.flush()
            await self.producer.close()

        Logger.base.info(f'[{self.service_name}] Async consumer stopped')
