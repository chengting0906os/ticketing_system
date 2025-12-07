"""
Base Kafka Consumer using confluent-kafka

High-performance consumer with:
- Multi-threaded message processing via ThreadPoolExecutor
- Manual offset commit for precise control
- Protobuf deserialization support
- OpenTelemetry tracing integration
- Dead Letter Queue (DLQ) support
"""

import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from confluent_kafka import Consumer, KafkaError, KafkaException, Message, Producer
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
    """
    Base class for high-performance Kafka consumers.

    Features:
    - Concurrent message processing with ThreadPoolExecutor
    - Small poll timeout (10ms) for low latency
    - Batch offset commits for efficiency
    - DLQ support for failed messages

    Subclasses must implement:
    - _get_topic_handlers(): Returns mapping of topic -> (proto_class, handler_func)
    - _initialize_dependencies(): Initialize use cases and other dependencies
    """

    # Configuration defaults (can be overridden by subclasses)
    POLL_TIMEOUT_SECONDS: float = 0.01  # 10ms - very low latency
    COMMIT_INTERVAL_SECONDS: float = 0.1  # 100ms
    MAX_WORKERS: int = 4  # Concurrent message handlers
    MAX_PENDING_COMMITS: int = 100  # Commit after this many messages

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

        self.consumer: Optional[Consumer] = None
        self.producer: Optional[Producer] = None  # For DLQ
        self.executor: Optional[ThreadPoolExecutor] = None
        self.portal: Optional['BlockingPortal'] = None
        self.tracer = trace.get_tracer(__name__)

        self.running = False
        self.stop_event = Event()

        # Offset tracking for manual commits
        self._pending_offsets: Dict[str, Dict[int, int]] = {}  # topic -> partition -> offset
        self._pending_count = 0
        self._last_commit_time = time.monotonic()

        # Track in-flight futures for graceful shutdown
        self._in_flight_futures: List[Future] = []

    def set_portal(self, portal: 'BlockingPortal') -> None:
        """Set BlockingPortal for calling async functions from sync code"""
        self.portal = portal

    @abstractmethod
    def _get_topic_handlers(self) -> Dict[str, tuple[type, Callable[[Dict], Any]]]:
        """
        Return mapping of topic name to (proto_class, handler_function).

        Example:
            return {
                'booking_topic': (pb.BookingEvent, self._handle_booking),
                'cancel_topic': (pb.CancelEvent, self._handle_cancel),
            }
        """
        pass

    @abstractmethod
    def _initialize_dependencies(self) -> None:
        """Initialize use cases and other dependencies before starting."""
        pass

    def _create_consumer(self) -> Consumer:
        """Create confluent-kafka Consumer with optimized settings."""
        base_config = {
            'bootstrap.servers': settings.KAFKA_BOOTSTRAP_SERVERS,
            'group.id': self.consumer_group_id,
            'auto.offset.reset': settings.KAFKA_CONSUMER_AUTO_OFFSET_RESET,
            'enable.auto.commit': False,  # Manual commit for precise control
            # Low latency settings
            'fetch.wait.max.ms': 10,  # Don't wait long for data
            'fetch.min.bytes': 1,  # Return immediately if any data available
            # Session management
            'session.timeout.ms': 45000,
            'heartbeat.interval.ms': 15000,
            # Connection retry
            'reconnect.backoff.ms': 1000,
            'reconnect.backoff.max.ms': 30000,
        }

        # Merge with any additional consumer config
        extra_config = self.kafka_config.consumer_config
        for key, value in extra_config.items():
            # Convert dot notation to confluent-kafka format
            base_config[key] = value

        return Consumer(base_config)

    def _create_producer(self) -> Producer:
        """Create producer for DLQ messages."""
        config = {
            'bootstrap.servers': settings.KAFKA_BOOTSTRAP_SERVERS,
            'acks': 'all',
            'retries': 3,
        }
        return Producer(config)

    def _deserialize_protobuf(self, msg: Message, proto_class: type) -> Dict:
        """Deserialize Kafka message value to dict via protobuf."""
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
        """Send failed message to Dead Letter Queue."""
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
            self.producer.poll(0)  # Trigger delivery callbacks

            Logger.base.warning(f'[DLQ] Sent to DLQ: {message.get("booking_id")} - {error}')

        except Exception as e:
            Logger.base.error(f'[DLQ] Failed to send: {e}')

    def _track_offset(self, msg: Message) -> None:
        """Track message offset for later batch commit."""
        topic = msg.topic()
        partition = msg.partition()
        offset = msg.offset() + 1  # Commit next offset

        if topic not in self._pending_offsets:
            self._pending_offsets[topic] = {}

        # Only track highest offset per partition
        current = self._pending_offsets[topic].get(partition, -1)
        if offset > current:
            self._pending_offsets[topic][partition] = offset

        self._pending_count += 1

    def _maybe_commit_offsets(self, force: bool = False) -> None:
        """Commit offsets if threshold reached or forced."""
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
            from confluent_kafka import TopicPartition

            offsets_to_commit = []
            for topic, partitions in self._pending_offsets.items():
                for partition, offset in partitions.items():
                    offsets_to_commit.append(TopicPartition(topic, partition, offset))

            if offsets_to_commit and self.consumer:
                self.consumer.commit(offsets=offsets_to_commit, asynchronous=False)
                Logger.base.debug(f'[{self.service_name}] Committed {self._pending_count} messages')

            # Reset tracking
            self._pending_offsets.clear()
            self._pending_count = 0
            self._last_commit_time = now

        except Exception as e:
            Logger.base.error(f'[{self.service_name}] Commit failed: {e}')

    def _process_message_wrapper(
        self,
        msg: Message,
        proto_class: type,
        handler: Callable[[Dict], Any],
        topic_name: str,
    ) -> None:
        """Wrapper to process message in thread pool."""
        try:
            # Calculate message age (time from produce to consume)
            msg_timestamp = msg.timestamp()
            if msg_timestamp and msg_timestamp[0] == 1:  # CreateTime
                produce_time_ms = msg_timestamp[1]
                now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                age_ms = now_ms - produce_time_ms
                if age_ms > 100:  # Only log if message is older than 100ms
                    Logger.base.warning(
                        f'[SLOW-CONSUME] topic={topic_name} partition={msg.partition()} '
                        f'age={age_ms}ms (message waited {age_ms}ms before being consumed)'
                    )

            # Deserialize
            message_dict = self._deserialize_protobuf(msg, proto_class)

            # Extract trace context
            extract_trace_context(
                headers={
                    'traceparent': message_dict.get('traceparent', ''),
                    'tracestate': message_dict.get('tracestate', ''),
                }
            )

            booking_id = message_dict.get('booking_id', 'unknown')

            with self.tracer.start_as_current_span(
                f'consumer.{topic_name}',
                attributes={
                    'messaging.system': 'kafka',
                    'messaging.operation': 'process',
                    'messaging.destination': topic_name,
                    'booking.id': booking_id,
                },
            ):
                # Call handler
                handler(message_dict)

                # Track offset for commit
                self._track_offset(msg)

        except Exception as e:
            Logger.base.error(f'[{self.service_name}] Processing error: {e}')
            # Send to DLQ
            try:
                message_dict = self._deserialize_protobuf(msg, proto_class)
            except Exception:
                message_dict = {'raw': msg.value().hex() if msg.value() else 'empty'}

            self._send_to_dlq(
                message=message_dict,
                original_topic=topic_name,
                error=str(e),
            )
            # Still track offset to avoid reprocessing
            self._track_offset(msg)

    def _cleanup_completed_futures(self) -> None:
        """Remove completed futures from tracking list."""
        self._in_flight_futures = [f for f in self._in_flight_futures if not f.done()]

    def start(self) -> None:
        """Start the consumer with retry mechanism."""
        max_retries = 5
        retry_delay = 2

        for attempt in range(1, max_retries + 1):
            try:
                # Initialize dependencies (use cases, etc.)
                self._initialize_dependencies()

                # Create consumer and producer
                self.consumer = self._create_consumer()
                self.producer = self._create_producer()

                # Get topic handlers
                topic_handlers = self._get_topic_handlers()
                topics = list(topic_handlers.keys())

                # Subscribe to topics
                self.consumer.subscribe(topics)

                Logger.base.info(
                    f'[{self.service_name}-{self.instance_id}] Started\n'
                    f'   Event: {self.event_id}\n'
                    f'   Group: {self.consumer_group_id}\n'
                    f'   Topics: {topics}\n'
                    f'   Workers: {self.MAX_WORKERS}'
                )

                # Create thread pool
                self.executor = ThreadPoolExecutor(
                    max_workers=self.MAX_WORKERS,
                    thread_name_prefix=f'{self.service_name}-worker',
                )

                self.running = True
                self._run_consumer_loop(topic_handlers)
                break

            except KafkaException as e:
                error_msg = str(e)

                if 'UNKNOWN_TOPIC_OR_PART' in error_msg and attempt < max_retries:
                    Logger.base.warning(
                        f'[{self.service_name}] Attempt {attempt}/{max_retries}: '
                        f'Topic not ready, retrying in {retry_delay}s...'
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    Logger.base.error(f'[{self.service_name}] Start failed: {e}')
                    raise

    def _run_consumer_loop(
        self, topic_handlers: Dict[str, tuple[type, Callable[[Dict], Any]]]
    ) -> None:
        """Main consumer loop with concurrent message processing."""
        while self.running and not self.stop_event.is_set():
            try:
                msg = self.consumer.poll(timeout=self.POLL_TIMEOUT_SECONDS)

                if msg is None:
                    # No message, check for commits
                    self._maybe_commit_offsets()
                    self._cleanup_completed_futures()
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    Logger.base.error(f'[{self.service_name}] Kafka error: {msg.error()}')
                    continue

                # Get handler for this topic
                topic = msg.topic()
                if topic not in topic_handlers:
                    Logger.base.warning(f'[{self.service_name}] Unknown topic: {topic}')
                    continue

                proto_class, handler = topic_handlers[topic]

                # Submit to thread pool for concurrent processing
                future = self.executor.submit(
                    self._process_message_wrapper,
                    msg,
                    proto_class,
                    handler,
                    topic,
                )
                self._in_flight_futures.append(future)

                # Periodic maintenance
                self._maybe_commit_offsets()
                self._cleanup_completed_futures()

            except Exception as e:
                Logger.base.error(f'[{self.service_name}] Loop error: {e}')
                time.sleep(0.1)  # Brief pause on error

    def stop(self) -> None:
        """Stop the consumer gracefully."""
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

        # Shutdown executor
        if self.executor:
            self.executor.shutdown(wait=True, cancel_futures=False)

        # Close consumer
        if self.consumer:
            try:
                self.consumer.close()
            except Exception as e:
                Logger.base.warning(f'[{self.service_name}] Close error: {e}')

        # Flush DLQ producer
        if self.producer:
            self.producer.flush(timeout=5.0)

        Logger.base.info(f'[{self.service_name}] Stopped')
