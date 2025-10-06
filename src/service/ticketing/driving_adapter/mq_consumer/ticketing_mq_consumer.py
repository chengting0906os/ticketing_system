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
"""

import json
import os
from typing import TYPE_CHECKING, Any, Dict

import anyio
from anyio.from_thread import BlockingPortal, start_blocking_portal
import anyio.to_thread
from confluent_kafka import Consumer


if TYPE_CHECKING:
    from anyio.from_thread import BlockingPortal

from src.platform.config.core_setting import settings
from src.platform.config.db_setting import get_async_session
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
        self.instance_id = os.getenv('CONSUMER_INSTANCE_ID', '1')
        self.consumer_group_id = os.getenv(
            'CONSUMER_GROUP_ID',
            KafkaConsumerGroupBuilder.ticketing_service(event_id=self.event_id),
        )

        # 創建 Kafka Consumer
        self.consumer = Consumer(
            {
                'bootstrap.servers': settings.KAFKA_BOOTSTRAP_SERVERS,
                'group.id': self.consumer_group_id,
                'enable.auto.commit': False,
                'auto.offset.reset': 'latest',
            }
        )

        # 訂閱 topics
        self.consumer.subscribe(
            [
                KafkaTopicBuilder.update_booking_status_to_pending_payment_and_ticket_status_to_reserved_in_postgresql(
                    event_id=self.event_id
                ),
                KafkaTopicBuilder.update_booking_status_to_failed(event_id=self.event_id),
            ]
        )

        self.running = False
        self.portal: Any = None

        # Use cases (延遲初始化)
        self.update_booking_to_pending_payment_use_case: Any = None
        self.update_booking_to_failed_use_case: Any = None

    def set_portal(self, portal: 'BlockingPortal') -> None:
        """設置 BlockingPortal 用於同步調用 async 函數"""
        self.portal = portal

    async def start(self):
        """使用 AnyIO 啟動消費者"""
        # 注意：MQ consumer 不使用 use cases
        # 每個消息處理都在獨立的 session 中執行（通過 _process_* 方法創建）

        Logger.base.info(
            f'🚀 [TICKETING] Started PostgreSQL state manager\n'
            f'   📊 Event: {self.event_id}\n'
            f'   👥 Group: {self.consumer_group_id}'
        )

        self.running = True

        try:
            while self.running:
                # 使用 anyio.to_thread 在線程池執行同步 poll
                msg = await anyio.to_thread.run_sync(
                    self.consumer.poll,
                    1.0,  # timeout
                )

                if msg is None:
                    continue

                if msg.error():
                    Logger.base.error(f'❌ [TICKETING] Kafka error: {msg.error()}')
                    continue

                # 異步路由處理
                await self._route_message(msg)

                # 手動 commit
                await anyio.to_thread.run_sync(self.consumer.commit, msg)

        except Exception as e:
            Logger.base.error(f'💥 [TICKETING] Consumer error: {e}')
            raise
        finally:
            await self.stop()

    async def _route_message(self, msg):
        """根據 topic 路由到對應處理器"""
        topic = msg.topic()

        try:
            value = json.loads(msg.value().decode('utf-8'))

            # 路由表
            if 'pending_payment_and' in topic:
                await self._process_pending_payment_and_reserved(value)
            elif 'failed' in topic:
                await self._process_failed(value)
            else:
                Logger.base.warning(f'⚠️ [TICKETING] Unknown topic: {topic}')

        except Exception as e:
            Logger.base.error(f'❌ [TICKETING] Route error: {e}')

    # ============================================================
    # Message Handlers
    # ============================================================

    @Logger.io
    async def _process_pending_payment_and_reserved(self, message: Dict[str, Any]):
        """處理 Booking → PENDING_PAYMENT + Ticket → RESERVED (原子操作)"""
        booking_id = message.get('booking_id')
        buyer_id = message.get('buyer_id')
        reserved_seats = message.get('reserved_seats', [])

        Logger.base.info(
            f'📥 [BOOKING+TICKET] Processing atomic update: '
            f'booking_id={booking_id}, buyer_id={buyer_id}, seats={len(reserved_seats)}'
        )

        # Create session for this message processing
        async for session in get_async_session():
            try:
                from src.platform.database.unit_of_work import SqlAlchemyUnitOfWork

                # Create UoW with session
                uow = SqlAlchemyUnitOfWork(session)

                # Create use case with UoW
                use_case = UpdateBookingToPendingPaymentAndTicketToReservedUseCase(uow=uow)

                # Execute use case (use case handles commit)
                await use_case.execute(
                    booking_id=booking_id or 0,
                    buyer_id=buyer_id or 0,
                    ticket_ids=reserved_seats,  # type: ignore[arg-type]
                )

                Logger.base.info(
                    f'✅ [BOOKING+TICKET] Atomic update completed: '
                    f'booking_id={booking_id}, tickets={len(reserved_seats)} reserved'
                )

            except Exception as e:
                Logger.base.error(f'❌ [BOOKING+TICKET] Failed: booking_id={booking_id}, error={e}')
                await session.rollback()

    @Logger.io
    async def _process_failed(self, message: Dict[str, Any]):
        """處理 Booking → FAILED"""
        booking_id = message.get('booking_id')
        buyer_id = message.get('buyer_id')
        reason = message.get('error_message', 'Unknown')

        Logger.base.info(f'📥 [BOOKING-FAILED] Processing: {booking_id} | Reason: {reason}')

        # Create session for this message processing
        async for session in get_async_session():
            try:
                from src.platform.database.unit_of_work import SqlAlchemyUnitOfWork

                # Create UoW with session
                uow = SqlAlchemyUnitOfWork(session)

                # Create use case with UoW
                use_case = UpdateBookingToFailedUseCase(uow=uow)

                # Execute use case (use case handles commit)
                await use_case.execute(
                    booking_id=booking_id or 0, buyer_id=buyer_id or 0, error_message=reason
                )

                Logger.base.info(f'✅ [BOOKING-FAILED] Updated: {booking_id}')

            except Exception as e:
                Logger.base.error(f'❌ [BOOKING-FAILED] Failed: booking_id={booking_id}, error={e}')
                await session.rollback()

    # ============================================================
    # Lifecycle
    # ============================================================

    async def stop(self):
        """停止服務"""
        if not self.running:
            return

        self.running = False

        try:
            Logger.base.info('🛑 [TICKETING] Stopping consumer...')
            await anyio.to_thread.run_sync(self.consumer.close)
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

            # 用 portal 執行 async start() - 直接傳遞方法引用
            portal.call(consumer.start)  # type: ignore[arg-type]

    except KeyboardInterrupt:
        Logger.base.info('⚠️ [TICKETING] Received interrupt signal')
        try:
            if consumer.portal:
                consumer.portal.call(consumer.stop)
        except Exception:
            pass
    except Exception as e:
        Logger.base.error(f'💥 [TICKETING] Consumer error: {e}')
        try:
            if consumer.portal:
                consumer.portal.call(consumer.stop)
        except:
            pass
    finally:
        Logger.base.info('🧹 Cleanup complete')


if __name__ == '__main__':
    main()
