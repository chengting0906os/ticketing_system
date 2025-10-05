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

import asyncio
import json
import os
from typing import Any, Dict

import anyio
import anyio.to_thread
from confluent_kafka import Consumer

from src.platform.config.core_setting import settings
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.kafka_constant_builder import (
    KafkaConsumerGroupBuilder,
    KafkaTopicBuilder,
)
from src.service.ticketing.app.command.update_booking_status_to_failed_use_case import (
    UpdateBookingToFailedUseCase,
)
from src.service.ticketing.app.command.update_booking_status_to_pending_payment_use_case import (
    UpdateBookingToPendingPaymentUseCase,
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

        # Use cases (延遲初始化)
        self.update_booking_to_pending_payment_use_case: Any = None
        self.update_booking_to_failed_use_case: Any = None

    async def start(self):
        """使用 AnyIO 啟動消費者"""
        # 初始化 use cases
        self.update_booking_to_pending_payment_use_case = UpdateBookingToPendingPaymentUseCase()
        self.update_booking_to_failed_use_case = UpdateBookingToFailedUseCase()

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

        try:
            # 直接將 reserved_seats 傳遞給 use case 處理
            # use case 會負責 seat_id → ticket_id 的映射和狀態更新
            await self.update_booking_to_pending_payment_use_case.execute(
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

    @Logger.io
    async def _process_failed(self, message: Dict[str, Any]):
        """處理 Booking → FAILED"""
        booking_id = message.get('booking_id')
        buyer_id = message.get('buyer_id')
        reason = message.get('error_message', 'Unknown')

        Logger.base.info(f'📥 [BOOKING-FAILED] Processing: {booking_id} | Reason: {reason}')

        try:
            await self.update_booking_to_failed_use_case.execute(
                booking_id=booking_id or 0, buyer_id=buyer_id or 0, error_message=reason
            )

            Logger.base.info(f'✅ [BOOKING-FAILED] Updated: {booking_id}')

        except Exception as e:
            Logger.base.error(f'❌ [BOOKING-FAILED] Failed: booking_id={booking_id}, error={e}')

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

    async def cleanup():
        try:
            await consumer.stop()
        except Exception as e:
            Logger.base.error(f'Cleanup error: {e}')

    try:
        asyncio.run(consumer.start())
    except KeyboardInterrupt:
        Logger.base.info('⚠️ [TICKETING] Received interrupt signal')
        asyncio.run(cleanup())
    except Exception as e:
        Logger.base.error(f'💥 [TICKETING] Consumer error: {e}')
        asyncio.run(cleanup())
    finally:
        Logger.base.info('🧹 Cleanup complete')


if __name__ == '__main__':
    main()
