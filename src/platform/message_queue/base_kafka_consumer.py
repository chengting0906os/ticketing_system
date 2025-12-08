from abc import ABC, abstractmethod
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from confluent_kafka import Consumer, KafkaError, KafkaException, Message, Producer, TopicPartition
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message as ProtoMessage
from opentelemetry import trace
import orjson


if TYPE_CHECKING:
    from anyio.from_thread import BlockingPortal

from src.platform.config.core_setting import KafkaConfig, settings
from src.platform.logging.loguru_io import Logger
from src.platform.observability.tracing import extract_trace_context


class BaseKafkaConsumer(ABC):
    # === Tuning Parameters (subclasses can override) ===
    #
    # POLL_TIMEOUT_SECONDS: Max time poll() waits for messages
    #   - Default: 0.05s (50ms)
    #   - Too long → high latency; Too short → CPU spin
    #
    # COMMIT_INTERVAL_SECONDS: How often to batch commit offsets
    #   - Default: 0.1s (100ms)
    #   - Too long → more reprocessing on restart; Too short → broker overhead
    #
    # MAX_WORKERS: ThreadPool concurrent worker count
    #   - Default: 4
    #   - Adjust based on CPU cores and IO intensity
    #
    # MAX_PENDING_COMMITS: Force commit after this many messages
    #   - Default: 100
    #   - Works with COMMIT_INTERVAL_SECONDS to control commit frequency
    #
    POLL_TIMEOUT_SECONDS: float = 0.05
    COMMIT_INTERVAL_SECONDS: float = 0.1
    MAX_WORKERS: int = 4
    MAX_PENDING_COMMITS: int = 100

    def __init__(
        self,
        *,
        service_name: str,
        consumer_group_id: str,
        event_id: int,
        dlq_topic: str,
    ) -> None:
        self.service_name = service_name
        self.event_id = event_id
        self.consumer_group_id = consumer_group_id
        self.dlq_topic = dlq_topic
        self.instance_id = settings.KAFKA_CONSUMER_INSTANCE_ID
        self.kafka_config = KafkaConfig(event_id=event_id, service=service_name)

        # Kafka clients
        self.consumer: Optional[Consumer] = None
        self.producer: Optional[Producer] = None  # For sending to DLQ
        self.executor: Optional[ThreadPoolExecutor] = None
        self.portal: Optional['BlockingPortal'] = None  # anyio cross-thread bridge
        self.tracer = trace.get_tracer(__name__)

        # Running state control
        self.running = False
        self.stop_event = Event()
        # Offset tracking (for batch commit) # Structure: { topic_name: { partition_id: next_offset_to_commit } }
        self._pending_offsets: Dict[str, Dict[int, int]] = {}
        self._pending_count = 0  # Messages pending commit
        self._last_commit_time = time.monotonic()
        self._in_flight_futures: List[Future] = []  # Track in-flight tasks (for graceful shutdown)

    def set_portal(self, portal: 'BlockingPortal') -> None:
        self.portal = portal

    @abstractmethod
    def _get_topic_handlers(self) -> Dict[str, tuple[type, Callable[[Dict], Any]]]:
        """
        Return topic name to handler mapping.

        Returns:
            {
                'topic-name': (ProtobufClass, handler_function),
                ...
            }

        Example:
            return {
                'booking-created': (pb.BookingCreatedEvent, self._handle_booking_created),
                'booking-cancelled': (pb.BookingCancelledEvent, self._handle_cancelled),
            }
        """
        pass

    @abstractmethod
    def _initialize_dependencies(self) -> None:
        """Initialize use cases and dependencies before consumer starts."""
        pass

    def _create_consumer(self) -> Consumer:
        """
        Create Kafka Consumer with optimized settings.

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

        return Consumer(base_config)

    def _create_producer(self) -> Producer:
        return Producer(
            {
                'bootstrap.servers': settings.KAFKA_BOOTSTRAP_SERVERS,
                'acks': 'all',  # Wait for all replicas to acknowledge
                'retries': 3,
            }
        )

    def _deserialize_protobuf(self, msg: Message, proto_class: type) -> Dict:
        proto_msg: ProtoMessage = proto_class()
        proto_msg.ParseFromString(msg.value())
        return MessageToDict(proto_msg, preserving_proto_field_name=True)

    def _send_to_dlq(
        self,
        *,
        message: Dict,
        original_topic: str,
        error: str,
        retry_count: int = 0,
    ) -> None:
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

            self.producer.produce(
                topic=self.dlq_topic,
                key=str(message.get('booking_id', 'unknown')).encode('utf-8'),
                value=orjson.dumps(dlq_message),
            )
            self.producer.poll(0)

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

    def _maybe_commit_offsets(self, *, force: bool = False) -> None:
        """
        Batch commit offsets.

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
                self.consumer.commit(offsets=offsets_to_commit, asynchronous=False)
                Logger.base.debug(f'[{self.service_name}] Committed {self._pending_count} offsets')

            self._pending_offsets.clear()
            self._pending_count = 0
            self._last_commit_time = now

        except Exception as e:
            Logger.base.error(f'[{self.service_name}] Commit failed: {e}')

    def _process_message(
        self,
        msg: Message,
        proto_class: type,
        handler: Callable[[Dict], Any],
        topic: str,
    ) -> None:
        """
        Process message in ThreadPool.

        Flow: deserialize → extract trace → call handler → track offset
        On error → send to DLQ
        """
        try:
            # Log slow messages (>100ms from produce to consume)
            ts = msg.timestamp()
            if ts and ts[0] == 1:  # CreateTime
                age_ms = int(datetime.now(timezone.utc).timestamp() * 1000) - ts[1]
                if age_ms > 100:
                    Logger.base.warning(f'[SLOW] {topic} p={msg.partition()} age={age_ms}ms')

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
                handler(data)
                self._track_offset(msg)

        except Exception as e:
            Logger.base.error(f'[{self.service_name}] Error: {e}')

            try:
                data = self._deserialize_protobuf(msg, proto_class)
            except Exception:
                data = {'raw': msg.value().hex() if msg.value() else 'empty'}

            self._send_to_dlq(message=data, original_topic=topic, error=str(e))
            self._track_offset(msg)  # Still track to avoid reprocessing

    def start(self) -> None:
        """Start consumer with retry for topic creation."""
        max_retries, delay = 5, 2

        for attempt in range(1, max_retries + 1):
            try:
                self._initialize_dependencies()
                self.consumer = self._create_consumer()
                self.producer = self._create_producer()

                handlers = self._get_topic_handlers()
                self.consumer.subscribe(list(handlers.keys()))

                Logger.base.info(
                    f'[{self.service_name}-{self.instance_id}] Started | '
                    f'event={self.event_id} group={self.consumer_group_id} '
                    f'topics={list(handlers.keys())} workers={self.MAX_WORKERS}'
                )

                self.executor = ThreadPoolExecutor(
                    max_workers=self.MAX_WORKERS,
                    thread_name_prefix=f'{self.service_name}-worker',
                )

                self.running = True
                self._run_loop(handlers)
                break

            except KafkaException as e:
                if 'UNKNOWN_TOPIC_OR_PART' in str(e) and attempt < max_retries:
                    Logger.base.warning(
                        f'[{self.service_name}] {attempt}/{max_retries}: Topic not ready, retry in {delay}s'
                    )
                    time.sleep(delay)
                    delay *= 2
                else:
                    Logger.base.error(f'[{self.service_name}] Start failed: {e}')
                    raise

    def _run_loop(self, handlers: Dict[str, tuple[type, Callable[[Dict], Any]]]) -> None:
        """
        Main consumer loop.

        1. poll() fetches next message (non-blocking, max POLL_TIMEOUT_SECONDS)
        2. No message → check if commit needed
        3. Has message → submit to ThreadPool for parallel processing
        """
        while self.running and not self.stop_event.is_set():
            try:
                msg = self.consumer.poll(timeout=self.POLL_TIMEOUT_SECONDS)

                if msg is None:
                    self._maybe_commit_offsets()
                    self._in_flight_futures = [f for f in self._in_flight_futures if not f.done()]
                    continue

                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        Logger.base.error(f'[{self.service_name}] Kafka error: {msg.error()}')
                    continue

                topic = msg.topic()
                if topic not in handlers:
                    continue

                proto_class, handler = handlers[topic]
                future = self.executor.submit(
                    self._process_message, msg, proto_class, handler, topic
                )
                self._in_flight_futures.append(future)

                self._maybe_commit_offsets()

            except Exception as e:
                Logger.base.error(f'[{self.service_name}] Loop error: {e}')
                time.sleep(0.1)

    def stop(self) -> None:
        """
        Graceful shutdown.

        Steps:
        1. Set stop flag
        2. Wait for in-flight messages to complete
        3. Final offset commit
        4. Shutdown ThreadPool
        5. Close Kafka consumer (triggers rebalance)
        6. Flush DLQ producer
        """
        if not self.running:
            return

        Logger.base.info(f'[{self.service_name}] Stopping...')

        self.running = False
        self.stop_event.set()

        # Wait for in-flight messages
        if self._in_flight_futures:
            Logger.base.info(
                f'[{self.service_name}] Waiting for {len(self._in_flight_futures)} in-flight messages'
            )
            for future in self._in_flight_futures:
                try:
                    future.result(timeout=5.0)
                except Exception as e:
                    Logger.base.warning(f'[{self.service_name}] Future error: {e}')

        # Final commit
        self._maybe_commit_offsets(force=True)

        # Shutdown ThreadPool
        if self.executor:
            self.executor.shutdown(wait=True, cancel_futures=False)

        # Close consumer (triggers rebalance, other consumers take over partitions)
        if self.consumer:
            try:
                self.consumer.close()
            except Exception as e:
                Logger.base.warning(f'[{self.service_name}] Close error: {e}')

        # Flush DLQ producer
        if self.producer:
            self.producer.flush(timeout=5.0)

        Logger.base.info(f'[{self.service_name}] Stopped')
