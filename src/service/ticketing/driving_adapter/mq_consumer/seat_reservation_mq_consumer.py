"""
Seat Reservation Consumer - 座位選擇路由器
職責:管理 Kvrocks 座位狀態並處理預訂請求

Features:
- 重試機制：指數退避 (exponential backoff)
- 死信隊列：無法處理的訊息發送至 DLQ
"""

import json
import os
import time
from typing import TYPE_CHECKING, Any, Dict, Optional
from uuid import UUID

from anyio.from_thread import BlockingPortal, start_blocking_portal
from opentelemetry import context as context_api
from opentelemetry import trace
from opentelemetry.propagate import extract
from quixstreams import Application


if TYPE_CHECKING:
    from anyio.from_thread import BlockingPortal

from src.platform.config.core_setting import settings
from src.platform.config.di import container
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.kafka_constant_builder import (
    KafkaConsumerGroupBuilder,
    KafkaTopicBuilder,
)
from src.platform.metrics.ticketing_metrics import metrics
from src.service.ticketing.app.command.finalize_seat_payment_use_case import (
    FinalizeSeatPaymentRequest,
)
from src.service.ticketing.app.dto import ReleaseSeatsBatchRequest
from src.service.ticketing.app.command.reserve_seats_use_case import ReservationRequest


# 移除 RetryConfig - 使用 Quix Streams 的 on_processing_error callback 處理錯誤


class KafkaConfig:
    """Kafka 配置 - 支援 Exactly-Once 語義"""

    def __init__(self, *, event_id: UUID, instance_id: str, retries: int = 3):
        """
        Args:
            event_id: 活動 ID
            instance_id: Consumer instance ID (用於生成唯一的 transactional.id)
            retries: Producer 重試次數
        """
        from src.platform.message_queue.kafka_constant_builder import (
            KafkaProducerTransactionalIdBuilder,
        )

        self.event_id = event_id
        self.instance_id = instance_id
        self.retries = retries
        self.transactional_id = KafkaProducerTransactionalIdBuilder.seat_reservation_service(
            event_id=event_id, instance_id=instance_id
        )

    @property
    def producer_config(self) -> Dict:
        """
        Producer 配置 - 啟用事務支援

        Note: Quix Streams with processing_guarantee='exactly-once' requires:
        - transactional.id: 唯一識別此 producer，實現 exactly-once
        - enable.idempotence = True (自動設置)
        - acks = 'all' (自動設置)
        """
        return {
            'transactional.id': self.transactional_id,  # 🔑 Exactly-Once 的關鍵
            'retries': self.retries,
        }

    @property
    def consumer_config(self) -> Dict:
        """
        Consumer 配置

        Note: Quix Streams with processing_guarantee='exactly-once' already sets:
        - enable.auto.commit = False (manual commit via transactions)
        - isolation.level = 'read_committed' (only read committed messages)

        We only set auto.offset.reset for first-time startup behavior:
        - 'latest': Skip old messages, start from newest (recommended for production)
        - 'earliest': Process all messages from beginning (use for testing/recovery)
        """
        return {
            'auto.offset.reset': 'latest',  # Changed from 'earliest' to prevent reprocessing
        }


class SeatReservationConsumer:
    """
    座位預訂消費者 - 無狀態路由器

    監聽 3 個 Topics:
    1. ticket_reserving_request_to_reserved_in_kvrocks - 預訂請求
    2. release_ticket_status_to_available_in_kvrocks - 釋放座位
    3. finalize_ticket_status_to_paid_in_kvrocks - 完成支付
    """

    def __init__(self):
        # Parse EVENT_ID as UUID (not int!)
        event_id_str = os.getenv('EVENT_ID', '00000000-0000-0000-0000-000000000001')
        self.event_id = UUID(event_id_str)

        # Generate unique instance_id per worker process using PID to avoid transactional.id conflicts
        base_instance_id = settings.KAFKA_CONSUMER_INSTANCE_ID
        self.instance_id = f'{base_instance_id}-pid-{os.getpid()}'
        self.consumer_group_id = os.getenv(
            'CONSUMER_GROUP_ID',
            KafkaConsumerGroupBuilder.seat_reservation_service(event_id=self.event_id),
        )

        self.kafka_config = KafkaConfig(event_id=self.event_id, instance_id=self.instance_id)
        self.kafka_app: Optional[Application] = None
        self.running = False
        self.portal: Optional['BlockingPortal'] = None

        # DLQ configuration
        self.dlq_topic = KafkaTopicBuilder.seat_reservation_dlq(event_id=self.event_id)

        # Use cases (延遲初始化)
        self.reserve_seats_use_case: Any = None
        self.release_seat_use_case: Any = None
        self.finalize_seat_payment_use_case: Any = None

        # OpenTelemetry tracer
        self.tracer = trace.get_tracer(__name__)

    def set_portal(self, portal: 'BlockingPortal') -> None:
        """設置 BlockingPortal 用於同步調用 async 函數"""
        self.portal = portal

    def _on_processing_error(self, exc: Exception, row: Any, _logger: Any) -> bool:
        """
        Quix Streams 錯誤處理 callback

        當訊息處理失敗時，此 callback 會被調用。

        Returns:
            True: 忽略錯誤，提交 offset（訊息被丟棄）
            False: 傳播錯誤，不提交 offset（停止 consumer，重啟後重試）

        注意：Quix Streams 的 callback 無法做到「跳過此訊息但不提交 offset」
        因此可重試錯誤會導致 consumer 停止，需要外部監控重啟
        """
        error_msg = str(exc)

        # 判斷是否為不可重試錯誤
        non_retryable_keywords = ['validation', 'invalid', 'not found', 'missing required']
        is_non_retryable = any(kw in error_msg.lower() for kw in non_retryable_keywords)

        if is_non_retryable:
            Logger.base.warning(f'⚠️ [ERROR-CALLBACK] Non-retryable error, sending to DLQ: {exc}')
            # 發送到 DLQ
            if row and hasattr(row, 'value'):
                message = row.value
                self._send_to_dlq(
                    message=message,
                    original_topic='unknown',  # Quix doesn't provide topic in callback
                    error=error_msg,
                    retry_count=0,
                )
            # 返回 True：提交 offset，跳過此訊息
            return True
        else:
            # 可重試錯誤：不提交 offset，停止 consumer
            # 外部監控（如 Kubernetes）會重啟 consumer，重新處理此訊息
            resource_exhaustion_keywords = [
                'too many clients',
                'connection pool',
                'max connections',
            ]
            is_resource_exhaustion = any(
                kw in error_msg.lower() for kw in resource_exhaustion_keywords
            )

            if is_resource_exhaustion:
                Logger.base.error(
                    f'❌ [ERROR-CALLBACK] Resource exhaustion, stopping consumer for restart: {exc}'
                )
            else:
                Logger.base.error(f'❌ [ERROR-CALLBACK] Retryable error, stopping consumer: {exc}')

            # 返回 False：不提交 offset，停止 consumer
            # 重啟後會重新處理此訊息
            return False

    @Logger.io
    def _create_kafka_app(self) -> Application:
        """創建支援 Exactly-Once 的 Kafka 應用，配置錯誤處理"""
        app = Application(
            broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=self.consumer_group_id,
            processing_guarantee='exactly-once',  # 🆕 啟用 exactly-once 處理
            commit_interval=0,  # 🆕 禁用自動提交間隔，讓事務管理
            producer_extra_config=self.kafka_config.producer_config,
            consumer_extra_config=self.kafka_config.consumer_config,
            on_processing_error=self._on_processing_error,  # 🆕 錯誤處理 callback
        )

        Logger.base.info(
            f'🪑 [SEAT-RESERVATION] Created exactly-once Kafka app\n'
            f'   👥 Group: {self.consumer_group_id}\n'
            f'   🎫 Event: {self.event_id}\n'
            f'   🔒 Processing: exactly-once\n'
            f'   🔑 Transactional ID: {self.kafka_config.transactional_id}\n'
            f'   ⚠️ Error handling: enabled'
        )
        return app

    @Logger.io
    def _setup_topics(self):
        """設置 3 個 topic 的處理邏輯 - 使用 Kafka 事務實現 Exactly Once"""
        if not self.kafka_app:
            self.kafka_app = self._create_kafka_app()

        # 定義 topic 配置
        topics = {
            'reservation': (
                KafkaTopicBuilder.ticket_reserving_request_to_reserved_in_kvrocks(
                    event_id=self.event_id
                ),
                self._process_reservation_request,
            ),
            'release': (
                KafkaTopicBuilder.release_ticket_status_to_available_in_kvrocks(
                    event_id=self.event_id
                ),
                self._process_release_seat,
            ),
            'finalize': (
                KafkaTopicBuilder.finalize_ticket_status_to_paid_in_kvrocks(event_id=self.event_id),
                self._process_finalize_payment,
            ),
        }

        # 註冊所有 topics - 使用 stateless 模式，依賴 Kafka 事務
        for name, (topic_name, handler) in topics.items():
            topic = self.kafka_app.topic(
                name=topic_name,
                key_serializer='str',
                value_serializer='json',
            )

            # 使用 stateless 處理，依賴 Kafka 事務的 exactly once 保證
            self.kafka_app.dataframe(topic=topic).apply(handler, stateful=False)
            Logger.base.info(f'   ✓ {name.capitalize()} topic configured (stateless + transaction)')

        Logger.base.info('✅ All topics configured (exactly once via Kafka transactions)')

    # ========== Retry and DLQ Helpers ==========

    @Logger.io
    def _send_to_dlq(self, *, message: Dict, original_topic: str, error: str, retry_count: int):
        """發送失敗訊息到 DLQ"""
        if not self.kafka_app:
            Logger.base.error('❌ [DLQ] Kafka app not initialized')
            return

        try:
            # 構建 DLQ 訊息（包含原始訊息和錯誤信息）
            dlq_message = {
                'original_message': message,
                'original_topic': original_topic,
                'error': error,
                'retry_count': retry_count,
                'timestamp': time.time(),
                'instance_id': self.instance_id,
            }

            # 發送到 DLQ（使用 aggregate_id 作為 key，保持順序）
            # 序列化訊息為 JSON
            serialized_message = json.dumps(dlq_message).encode('utf-8')

            with self.kafka_app.get_producer() as producer:
                producer.produce(
                    topic=self.dlq_topic,
                    key=str(message.get('aggregate_id', 'unknown')),
                    value=serialized_message,
                )

            Logger.base.warning(
                f'📮 [DLQ] Sent to DLQ: {message.get("aggregate_id")} '
                f'after {retry_count} retries, error: {error}'
            )

        except Exception as e:
            Logger.base.error(f'❌ [DLQ] Failed to send to DLQ: {e}')

    # ========== Message Handlers ==========

    @Logger.io
    def _process_reservation_request(
        self, message: Dict, key: Any = None, context: Any = None
    ) -> Dict:
        """
        處理預訂請求 - 簡化版，錯誤由 on_processing_error callback 處理

        Note: 不做應用層重試，讓 Quix Streams 的 error callback 處理錯誤
        這樣不會阻塞 consumer
        """
        start_time = time.time()
        event_id = message.get('event_id', self.event_id)
        section = message.get('section', 'unknown')
        mode = message.get('seat_selection_mode', 'unknown')
        booking_id = message.get('booking_id', 'unknown')

        # Extract partition info from Quix Streams context
        partition_info = ''
        if hasattr(context, 'topic') and hasattr(context, 'partition'):
            partition_info = f' | partition={context.partition}, offset={context.offset}'

        # Extract trace context from Kafka message headers
        headers_dict = {}
        if hasattr(context, 'headers') and context.headers:
            # Convert Kafka headers (list of tuples) to dict for extract()
            for key_bytes, value_bytes in context.headers:
                if isinstance(key_bytes, bytes):
                    key_str = key_bytes.decode('utf-8')
                else:
                    key_str = str(key_bytes)

                if isinstance(value_bytes, bytes):
                    value_str = value_bytes.decode('utf-8')
                else:
                    value_str = str(value_bytes)

                headers_dict[key_str] = value_str

        # Extract trace context and create span
        ctx = extract(headers_dict)  # Extract propagated trace context

        # IMPORTANT: Create a wrapper that preserves the span context for async call
        # BlockingPortal.call() doesn't automatically propagate OpenTelemetry context
        span = self.tracer.start_span(
            'consumer.process_reservation',
            context=ctx,  # Link to producer's trace
            attributes={
                'messaging.system': 'kafka',
                'messaging.operation': 'process',
                'booking.id': str(booking_id),
                'event.id': str(event_id),
                'seat.selection_mode': mode,
                'partition': context.partition if hasattr(context, 'partition') else -1,
            },
        )

        with trace.use_span(span, end_on_exit=True):
            # Attach span to current context so portal.call() can access it
            Logger.base.info(
                f'\033[94m🎫 [RESERVATION-{self.instance_id}] Processing: booking_id={booking_id}{partition_info}\033[0m'
            )

            # Get current OpenTelemetry context to pass to async function
            current_context = trace.get_current_span().get_span_context()

            # 執行預訂邏輯（拋出異常會被 on_processing_error 捕獲）
            # pyrefly: ignore  # missing-attribute
            # Pass trace context explicitly to async function
            result = self.portal.call(self._handle_reservation_async, message, current_context)

            # 記錄成功的預訂
            processing_time = time.time() - start_time
            metrics.record_seat_reservation(
                event_id=event_id,
                section=section,
                mode=mode,
                result='success',
                duration=processing_time,
            )

            span.set_status(trace.Status(trace.StatusCode.OK))
            span.add_event('Reservation processed successfully')

            return {'success': True, 'result': result}

    @Logger.io
    def _process_release_seat(self, message: Dict, key: Any = None, context: Any = None) -> Dict:
        """處理釋放座位 - 支援 DLQ（釋放操作通常不需要重試）"""
        # Extract partition info
        partition_info = ''
        if hasattr(context, 'partition'):
            partition_info = f' | partition={context.partition}'

        # Handle both old format (seat_id) and new format (seat_positions)
        seat_id = message.get('seat_id')
        seat_positions = message.get('seat_positions', [])

        if seat_id:
            # Legacy single seat release
            seat_positions = [seat_id]
        elif not seat_positions:
            error_msg = 'Missing seat_id or seat_positions'
            self._send_to_dlq(
                message=message,
                original_topic='release_ticket_status_to_available_in_kvrocks',
                error=error_msg,
                retry_count=0,
            )
            return {'success': False, 'error': error_msg, 'sent_to_dlq': True}

        try:
            # PERFORMANCE OPTIMIZATION: Release all seats in a SINGLE batch call
            # instead of N sequential calls to reduce portal overhead
            Logger.base.info(
                f'🔓 [RELEASE-{self.instance_id}] Releasing {len(seat_positions)} seats in batch{partition_info}'
            )

            batch_request = ReleaseSeatsBatchRequest(
                seat_ids=seat_positions, event_id=self.event_id
            )
            # pyrefly: ignore  # missing-attribute
            result = self.portal.call(self.release_seat_use_case.execute_batch, batch_request)

            # Log results
            if result.successful_seats:
                Logger.base.info(
                    f'✅ [RELEASE-{self.instance_id}] Released {result.total_released}/{len(seat_positions)} seats'
                )

            if result.failed_seats:
                Logger.base.warning(
                    f'⚠️ [RELEASE-{self.instance_id}] Failed to release {len(result.failed_seats)} seats: {result.failed_seats}'
                )

            return {
                'success': True,
                'released_seats': result.successful_seats,
                'failed_seats': result.failed_seats,
                'total_released': result.total_released,
            }

        except Exception as e:
            Logger.base.error(f'❌ [RELEASE] {e}')
            # 發送到 DLQ
            self._send_to_dlq(
                message=message,
                original_topic='release_ticket_status_to_available_in_kvrocks',
                error=str(e),
                retry_count=0,
            )
            return {'success': False, 'error': str(e), 'sent_to_dlq': True}

    @Logger.io
    def _process_finalize_payment(
        self, message: Dict, key: Any = None, context: Any = None
    ) -> Dict:
        """處理完成支付 - 支援 DLQ（支付完成操作通常不需要重試）"""
        # Extract partition info
        partition_info = ''
        if hasattr(context, 'partition'):
            partition_info = f' | partition={context.partition}'

        seat_id = message.get('seat_id')
        if not seat_id:
            error_msg = 'Missing seat_id'
            self._send_to_dlq(
                message=message,
                original_topic='finalize_ticket_status_to_paid_in_kvrocks',
                error=error_msg,
                retry_count=0,
            )
            return {'success': False, 'error': error_msg, 'sent_to_dlq': True}

        try:
            request = FinalizeSeatPaymentRequest(
                seat_id=seat_id,
                event_id=self.event_id,
                timestamp=message.get('timestamp', ''),
            )

            # pyrefly: ignore  # missing-attribute
            result = self.portal.call(self.finalize_seat_payment_use_case.execute, request)

            if result.success:
                Logger.base.info(f'💰 [FINALIZE-{self.instance_id}] {seat_id}{partition_info}')
                return {'success': True, 'seat_id': seat_id}

            # Use case 執行失敗，發送到 DLQ
            self._send_to_dlq(
                message=message,
                original_topic='finalize_ticket_status_to_paid_in_kvrocks',
                error=result.error_message or 'Unknown error',
                retry_count=0,
            )
            return {'success': False, 'error': result.error_message, 'sent_to_dlq': True}

        except Exception as e:
            Logger.base.error(f'❌ [FINALIZE] {e}')
            # 發送到 DLQ
            self._send_to_dlq(
                message=message,
                original_topic='finalize_ticket_status_to_paid_in_kvrocks',
                error=str(e),
                retry_count=0,
            )
            return {'success': False, 'error': str(e), 'sent_to_dlq': True}

    # ========== Reservation Logic ==========

    @Logger.io
    async def _handle_reservation_async(
        self, event_data: Any, parent_span_context: Any = None
    ) -> bool:
        """
        處理座位預訂事件 - 只負責路由到 use case

        Note: 不捕獲異常，讓它傳播到上層的重試邏輯
        """
        # Restore parent trace context if provided
        if parent_span_context:
            ctx = trace.set_span_in_context(trace.NonRecordingSpan(parent_span_context))
            token = context_api.attach(ctx)
        else:
            token = None

        try:
            parsed = self._parse_event_data(event_data)
            if not parsed:
                error_msg = 'Failed to parse event data'
                Logger.base.error(f'❌ [RESERVATION] {error_msg}')
                raise ValueError(error_msg)

            command = self._create_reservation_command(parsed)
            Logger.base.info(f'🎯 [RESERVATION] booking_id={command["booking_id"]}')

            await self._execute_reservation(command)
            return True
        finally:
            if token:
                context_api.detach(token)

    @Logger.io
    def _parse_event_data(self, event_data: Any) -> Optional[Dict]:
        """解析事件數據"""
        try:
            if isinstance(event_data, dict):
                return event_data
            if isinstance(event_data, str):
                return json.loads(event_data)
            if hasattr(event_data, '__dict__'):
                return dict(vars(event_data))

            Logger.base.error(f'❌ Unknown event data type: {type(event_data)}')
            return None

        except Exception as e:
            Logger.base.error(f'❌ Parse failed: {e}')
            return None

    @Logger.io
    def _create_reservation_command(self, event_data: Dict) -> Dict:
        """創建預訂命令

        Note: publish_domain_event spreads event fields with **event.__dict__
        and removes 'aggregate_id' to avoid duplication. All fields including
        booking_id, buyer_id, event_id are at top level.
        """
        booking_id = event_data.get('booking_id')
        buyer_id = event_data.get('buyer_id')
        event_id = event_data.get('event_id')

        if not all([booking_id, buyer_id, event_id]):
            raise ValueError('Missing required fields in event data')

        # Convert string UUIDs from Kafka back to UUID objects for cassandra-driver
        return {
            'booking_id': UUID(booking_id) if isinstance(booking_id, str) else booking_id,
            'buyer_id': UUID(buyer_id) if isinstance(buyer_id, str) else buyer_id,
            'event_id': UUID(event_id) if isinstance(event_id, str) else event_id,
            'section': event_data.get('section', ''),
            'subsection': event_data.get('subsection', 0),
            'quantity': event_data.get('quantity', 2),
            'seat_selection_mode': event_data.get('seat_selection_mode', 'best_available'),
            'seat_positions': event_data.get('seat_positions', []),
        }

    @Logger.io
    async def _execute_reservation(self, command: Dict) -> bool:
        """執行座位預訂 - 只負責調用 use case"""
        try:
            Logger.base.info(
                f'🪑 [EXECUTE] booking={command["booking_id"]}, '
                f'section={command["section"]}-{command["subsection"]}, '
                f'qty={command["quantity"]}, mode={command["seat_selection_mode"]}'
            )

            request = ReservationRequest(
                booking_id=command['booking_id'],
                buyer_id=command['buyer_id'],
                event_id=command['event_id'],
                selection_mode=command['seat_selection_mode'],
                quantity=command['quantity'],
                seat_positions=command['seat_positions'],
                section_filter=command['section'],
                subsection_filter=command['subsection'],
            )

            # 調用 use case (use case 會負責發送成功/失敗事件)
            await self.reserve_seats_use_case.reserve_seats(request)
            return True

        except Exception as e:
            Logger.base.error(f'❌ [EXECUTE] Exception: {e}')
            return False

    # ========== Lifecycle ==========

    def start(self):
        """啟動服務 - 支援 topic metadata 同步重試"""
        max_retries = 5
        retry_delay = 2  # seconds

        for attempt in range(1, max_retries + 1):
            try:
                # 初始化 use cases
                self.reserve_seats_use_case = container.reserve_seats_use_case()
                self.release_seat_use_case = container.release_seat_use_case()
                self.finalize_seat_payment_use_case = container.finalize_seat_payment_use_case()

                # 設置 Kafka
                self._setup_topics()

                Logger.base.info(
                    f'🚀 [SEAT-RESERVATION-{self.instance_id}] Started\n'
                    f'   📊 Event: {self.event_id}\n'
                    f'   👥 Group: {self.consumer_group_id}\n'
                    f'   🔒 Processing: exactly-once\n'
                    f'   📦 Waiting for partition assignment...'
                )

                self.running = True
                if self.kafka_app:
                    Logger.base.info(
                        f'🎯 [SEAT-RESERVATION-{self.instance_id}] Running app\n'
                        f'   💡 Partition assignments will be logged when messages are processed'
                    )
                    self.kafka_app.run()
                    break  # Success, exit retry loop

            except Exception as e:
                error_msg = str(e)

                # Check if it's a topic metadata sync issue
                if 'UNKNOWN_TOPIC_OR_PART' in error_msg and attempt < max_retries:
                    Logger.base.warning(
                        f'⚠️ [SEAT-RESERVATION] Attempt {attempt}/{max_retries} failed: Topic metadata not ready\n'
                        f'   🔄 Retrying in {retry_delay}s... (Kafka brokers may still be syncing)'
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff

                    # Reset kafka_app for next attempt
                    self.kafka_app = None
                    continue
                else:
                    # Fatal error or max retries reached
                    Logger.base.error(
                        f'❌ [SEAT-RESERVATION] Start failed after {attempt} attempts: {e}'
                    )
                    raise

    def stop(self):
        """停止服務"""
        if not self.running:
            return

        self.running = False

        if self.kafka_app:
            try:
                Logger.base.info('🛑 Stopping Kafka app...')
                self.kafka_app = None
            except Exception as e:
                Logger.base.warning(f'⚠️ Stop error: {e}')

        Logger.base.info('🛑 Consumer stopped')


def main():
    consumer = SeatReservationConsumer()
    try:
        # 啟動 BlockingPortal，創建共享的 event loop
        with start_blocking_portal() as portal:
            consumer.set_portal(portal)
            consumer.start()

    except KeyboardInterrupt:
        Logger.base.info('⚠️ Received interrupt signal')
        try:
            consumer.stop()
        except Exception:
            pass
    except Exception as e:
        Logger.base.error(f'💥 Consumer error: {e}')
        try:
            consumer.stop()
        except:
            pass
    finally:
        Logger.base.info('🧹 Cleaning up resources...')


if __name__ == '__main__':
    main()
