"""
Ticketing MQ Consumer - Unified PostgreSQL State Manager
票務 MQ 消費者 - 統一 PostgreSQL 狀態管理器

整合職責 (2 個 topics)：
1. Booking + Ticket 狀態同步 (原子操作):
   - pending_payment_and_reserved: 座位預訂成功後，同時更新 Booking 為 PENDING_PAYMENT 和 Ticket 為 RESERVED

2. Booking 失敗處理:
   - failed: 座位預訂失敗後更新訂單狀態

重要：
- 這個 consumer **只操作 PostgreSQL**，不碰 Kvrocks！
- Kvrocks 狀態管理是 seat_reservation_consumer 的職責
- 合併 topic 確保 Booking 和 Ticket 狀態更新的原子性

Features:
- 錯誤處理：使用 Quix Streams callback 處理錯誤
- 死信隊列：無法處理的訊息發送至 DLQ
"""

import json
import os
import time
from typing import TYPE_CHECKING, Any, Dict, Optional

from anyio.from_thread import BlockingPortal, start_blocking_portal
from quixstreams import Application


if TYPE_CHECKING:
    from anyio.from_thread import BlockingPortal

from src.platform.config.core_setting import settings
from src.platform.database.db_setting import get_async_session
from src.platform.database.unit_of_work import SqlAlchemyUnitOfWork
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.kafka_constant_builder import (
    KafkaConsumerGroupBuilder,
    KafkaTopicBuilder,
)
from src.service.ticketing.app.command.update_booking_status_to_failed_use_case import (
    UpdateBookingToFailedUseCase,
)
from src.service.ticketing.app.command.update_booking_status_to_pending_payment_and_ticket_to_reserved_use_case import (
    UpdateBookingToPendingPaymentAndTicketToReservedUseCase,
)


class KafkaConfig:
    """Kafka 配置 - 支援 Exactly-Once 語義"""

    def __init__(self, *, event_id: int, instance_id: str, retries: int = 3):
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
        self.transactional_id = KafkaProducerTransactionalIdBuilder.ticketing_service(
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
            'auto.offset.reset': 'latest',
        }


class TicketingMqConsumer:
    """
    整合的票務 MQ 消費者 (PostgreSQL 狀態管理)

    處理 2 個 topics：
    - Booking + Ticket 原子更新 (pending_payment + reserved)
    - Booking 失敗處理 (failed)

    全部都是 PostgreSQL 操作，無狀態處理
    """

    def __init__(self):
        self.event_id = int(os.getenv('EVENT_ID', '1'))
        self.instance_id = settings.KAFKA_CONSUMER_INSTANCE_ID
        self.consumer_group_id = os.getenv(
            'CONSUMER_GROUP_ID',
            KafkaConsumerGroupBuilder.ticketing_service(event_id=self.event_id),
        )

        self.kafka_config = KafkaConfig(event_id=self.event_id, instance_id=self.instance_id)
        self.kafka_app: Optional[Application] = None
        self.running = False
        self.portal: Optional['BlockingPortal'] = None

        # DLQ configuration
        self.dlq_topic = KafkaTopicBuilder.ticketing_dlq(event_id=self.event_id)

        # Use cases (延遲初始化)
        self.update_booking_to_pending_payment_use_case: Any = None
        self.update_booking_to_failed_use_case: Any = None

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
        non_retryable_keywords = [
            'validation',
            'invalid',
            'not found',
            'missing required',
            'constraint',
        ]
        is_non_retryable = any(kw in error_msg.lower() for kw in non_retryable_keywords)

        if is_non_retryable:
            Logger.base.warning(
                f'⚠️ [TICKETING-ERROR-CALLBACK] Non-retryable error, sending to DLQ: {exc}'
            )
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
                    f'❌ [TICKETING-ERROR-CALLBACK] Resource exhaustion, stopping consumer for restart: {exc}'
                )
            else:
                Logger.base.error(
                    f'❌ [TICKETING-ERROR-CALLBACK] Retryable error, stopping consumer: {exc}'
                )

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
            f'🎫 [TICKETING] Created exactly-once Kafka app\n'
            f'   👥 Group: {self.consumer_group_id}\n'
            f'   🎫 Event: {self.event_id}\n'
            f'   🔒 Processing: exactly-once\n'
            f'   🔑 Transactional ID: {self.kafka_config.transactional_id}\n'
            f'   ⚠️ Error handling: enabled'
        )
        return app

    @Logger.io
    def _setup_topics(self):
        """設置 2 個 topic 的處理邏輯 - 使用 Kafka 事務實現 Exactly Once"""
        if not self.kafka_app:
            self.kafka_app = self._create_kafka_app()

        # 定義 topic 配置
        topics = {
            'pending_payment_and_reserved': (
                KafkaTopicBuilder.update_booking_status_to_pending_payment_and_ticket_status_to_reserved_in_postgresql(
                    event_id=self.event_id
                ),
                self._process_pending_payment_and_reserved,
            ),
            'failed': (
                KafkaTopicBuilder.update_booking_status_to_failed(event_id=self.event_id),
                self._process_failed,
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

    # ========== DLQ Helper ==========

    @Logger.io
    def _send_to_dlq(self, *, message: Dict, original_topic: str, error: str, retry_count: int):
        """發送失敗訊息到 DLQ"""
        if not self.kafka_app:
            Logger.base.error('❌ [TICKETING-DLQ] Kafka app not initialized')
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

            # 發送到 DLQ（使用 booking_id 作為 key，保持順序）
            serialized_message = json.dumps(dlq_message).encode('utf-8')

            with self.kafka_app.get_producer() as producer:
                producer.produce(
                    topic=self.dlq_topic,
                    key=str(message.get('booking_id', 'unknown')),
                    value=serialized_message,
                )

            Logger.base.warning(
                f'📮 [TICKETING-DLQ] Sent to DLQ: booking_id={message.get("booking_id")} '
                f'after {retry_count} retries, error: {error}'
            )

        except Exception as e:
            Logger.base.error(f'❌ [TICKETING-DLQ] Failed to send to DLQ: {e}')

    # ========== Message Handlers ==========

    @Logger.io
    def _process_pending_payment_and_reserved(
        self, message: Dict, key: Any = None, context: Any = None
    ) -> Dict:
        """處理 Booking → PENDING_PAYMENT + Ticket → RESERVED (原子操作)"""
        booking_id = message.get('booking_id')
        reserved_seats = message.get('reserved_seats', [])

        # Extract partition info from Quix Streams context
        partition_info = ''
        if hasattr(context, 'partition'):
            partition_info = f' | partition={context.partition}'

        try:
            Logger.base.info(
                f'📥 [BOOKING+TICKET-{self.instance_id}] Processing: booking_id={booking_id}{partition_info}'
            )

            # Use portal to call async function (same pattern as seat_reservation)
            self.portal.call(self._handle_pending_payment_and_reserved_async, message)

            Logger.base.info(
                f'✅ [BOOKING+TICKET] Completed: booking_id={booking_id}, tickets={len(reserved_seats)}'
            )
            return {'success': True}

        except Exception as e:
            Logger.base.error(f'❌ [BOOKING+TICKET] Failed: booking_id={booking_id}, error={e}')
            return {'success': False, 'error': str(e)}

    async def _handle_pending_payment_and_reserved_async(self, message: Dict[str, Any]):
        """Async handler for pending payment and reserved"""
        booking_id = message.get('booking_id')
        buyer_id = message.get('buyer_id')
        reserved_seats = message.get('reserved_seats', [])

        # Create session for this message processing
        async for session in get_async_session():
            try:
                # Create UoW with session
                uow = SqlAlchemyUnitOfWork(session)

                # Create use case with UoW
                use_case = UpdateBookingToPendingPaymentAndTicketToReservedUseCase(uow=uow)

                # Execute use case (use case handles commit)
                await use_case.execute(
                    booking_id=booking_id or 0,
                    buyer_id=buyer_id or 0,
                    seat_identifiers=reserved_seats,
                )

            except Exception as e:
                Logger.base.error(f'❌ [BOOKING+TICKET] DB Error: {e}')
                await session.rollback()
                raise

    @Logger.io
    def _process_failed(self, message: Dict, key: Any = None, context: Any = None) -> Dict:
        """處理 Booking → FAILED"""
        booking_id = message.get('booking_id')

        # Extract partition info from Quix Streams context
        partition_info = ''
        if hasattr(context, 'partition'):
            partition_info = f' | partition={context.partition}'

        try:
            Logger.base.info(
                f'📥 [BOOKING-FAILED-{self.instance_id}] Processing: booking_id={booking_id}{partition_info}'
            )

            # Use portal to call async function (same pattern as seat_reservation)
            self.portal.call(self._handle_failed_async, message)

            Logger.base.info(f'✅ [BOOKING-FAILED] Completed: {booking_id}')
            return {'success': True}

        except Exception as e:
            Logger.base.error(f'❌ [BOOKING-FAILED] Failed: booking_id={booking_id}, error={e}')
            return {'success': False, 'error': str(e)}

    async def _handle_failed_async(self, message: Dict[str, Any]):
        """Async handler for failed booking"""
        booking_id = message.get('booking_id')
        buyer_id = message.get('buyer_id')
        reason = message.get('error_message', 'Unknown')

        # Create session for this message processing
        async for session in get_async_session():
            try:
                # Create UoW with session
                uow = SqlAlchemyUnitOfWork(session)

                # Create use case with UoW
                use_case = UpdateBookingToFailedUseCase(uow=uow)

                # Execute use case (use case handles commit)
                await use_case.execute(
                    booking_id=booking_id or 0, buyer_id=buyer_id or 0, error_message=reason
                )

            except Exception as e:
                Logger.base.error(f'❌ [BOOKING-FAILED] DB Error: {e}')
                await session.rollback()
                raise

    # ========== Lifecycle ==========

    def start(self):
        """啟動服務 - 支援 topic metadata 同步重試"""
        import time

        max_retries = 5
        retry_delay = 2  # seconds

        for attempt in range(1, max_retries + 1):
            try:
                # 設置 Kafka topics
                self._setup_topics()

                Logger.base.info(
                    f'🚀 [TICKETING-{self.instance_id}] Started\n'
                    f'   📊 Event: {self.event_id}\n'
                    f'   👥 Group: {self.consumer_group_id}\n'
                    f'   🔒 Processing: exactly-once\n'
                    f'   📦 Waiting for partition assignment...'
                )

                self.running = True
                if self.kafka_app:
                    Logger.base.info(
                        f'🎯 [TICKETING-{self.instance_id}] Running app\n'
                        f'   💡 Partition assignments will be logged when messages are processed'
                    )
                    self.kafka_app.run()
                    break  # Success, exit retry loop

            except Exception as e:
                error_msg = str(e)

                # Check if it's a topic metadata sync issue
                if 'UNKNOWN_TOPIC_OR_PART' in error_msg and attempt < max_retries:
                    Logger.base.warning(
                        f'⚠️ [TICKETING] Attempt {attempt}/{max_retries} failed: Topic metadata not ready\n'
                        f'   🔄 Retrying in {retry_delay}s... (Kafka brokers may still be syncing)'
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff

                    # Reset kafka_app for next attempt
                    self.kafka_app = None
                    continue
                else:
                    # Fatal error or max retries reached
                    Logger.base.error(f'❌ [TICKETING] Start failed after {attempt} attempts: {e}')
                    raise

    def stop(self):
        """停止服務"""
        if not self.running:
            return

        self.running = False

        try:
            Logger.base.info('🛑 [TICKETING] Stopping consumer...')
            if self.kafka_app:
                self.kafka_app.stop()
            Logger.base.info('✅ [TICKETING] Consumer stopped')
        except Exception as e:
            Logger.base.warning(f'⚠️ [TICKETING] Stop error: {e}')


# ============================================================
# Main Entry Point
# ============================================================


def main():
    """主程序入口"""
    consumer = TicketingMqConsumer()

    try:
        # 啟動 BlockingPortal，創建共享的 event loop
        with start_blocking_portal() as portal:
            consumer.set_portal(portal)
            consumer.start()

    except KeyboardInterrupt:
        Logger.base.info('⚠️ [TICKETING] Received interrupt signal')
        try:
            consumer.stop()
        except Exception:
            pass
    except Exception as e:
        Logger.base.error(f'💥 [TICKETING] Consumer error: {e}')
        try:
            consumer.stop()
        except:
            pass
    finally:
        Logger.base.info('🧹 Cleaning up resources...')


if __name__ == '__main__':
    main()
