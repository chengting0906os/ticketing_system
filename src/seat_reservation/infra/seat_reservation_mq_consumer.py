"""
Seat Reservation Consumer - Seat Selection Router
座位預訂服務消費者 - 座位選擇路由器

職責：
- 管理 Kvrocks 座位狀態 (Bitfield + Counter 存儲)
- 處理座位初始化和狀態變更
- 執行座位選擇算法
- 維護 section 統計資訊

架構：
- 使用 Kvrocks Bitfield 存儲座位狀態 (2 bits per seat)
- 使用 Counter 優化查詢 (row/subsection level)
- 無狀態 Kafka consumer (state 存在 Kvrocks)
"""

import asyncio
import os
import time
from typing import Dict, Optional

import anyio
from quixstreams import Application
import redis

from src.platform.config.core_setting import settings
from src.platform.config.di import container
from src.platform.logging.loguru_io import Logger
from src.platform.message_queue.kafka_constant_builder import (
    KafkaConsumerGroupBuilder,
    KafkaTopicBuilder,
)
from src.seat_reservation.infra.seat_state_store import seat_state_store


# Kafka 配置
KAFKA_COMMIT_INTERVAL = 0.5
KAFKA_RETRIES = 3

# Section stats TTL (30 days)
SECTION_STATS_TTL = 86400 * 30  # 2,592,000 seconds


class SeatReservationConsumer:
    """
    座位預訂消費者 - 負責管理座位狀態和處理預訂請求

    職責：
    - 管理 Kvrocks 座位狀態 (Bitfield + Counter 存儲)
    - 接收來自 booking 的預訂請求
    - 執行座位選擇算法
    - 發布預訂結果到 event_ticketing

    監聽的 4 個 Topics:
    1. seat_initialization_command_in_kvrocks - 座位初始化
    2. ticket_reserving_request_to_reserved_in_kvrocks - 預訂請求
    3. release_ticket_status_to_available_in_kvrocks - 釋放座位
    4. finalize_ticket_status_to_paid_in_kvrocks - 完成支付
    """

    def __init__(self):
        self.kafka_app = None
        self.gateway = None
        self.running = False
        self.event_id = int(os.getenv('EVENT_ID', '1'))
        self.consumer_group_id = os.getenv(
            'CONSUMER_GROUP_ID',
            KafkaConsumerGroupBuilder.seat_reservation_service(event_id=self.event_id),
        )
        self.instance_id = os.getenv('CONSUMER_INSTANCE_ID', '1')

    def _create_kafka_app(self):
        """
        創建 Kafka 應用 (無狀態)

        與 EventTicketing 不同，Seat Reservation 不使用 Quix Streams 的 stateful processing
        所有狀態直接存儲在 Kvrocks，Consumer 只負責路由和協調
        """
        app = Application(
            broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=self.consumer_group_id,
            commit_interval=KAFKA_COMMIT_INTERVAL,
            producer_extra_config={
                'enable.idempotence': True,
                'acks': 'all',
                'retries': KAFKA_RETRIES,
            },
            consumer_extra_config={
                'enable.auto.commit': False,
                'auto.offset.reset': 'earliest',
            },
        )

        Logger.base.info('🪑 [SEAT-RESERVATION] Created Kafka app (stateless)')
        Logger.base.info(f'👥 Consumer group: {self.consumer_group_id}')
        return app

    def _setup_kafka_processing(self):
        """設置 Kafka processing - 處理 4 個 topics (無狀態)"""
        if not self.kafka_app:
            self.kafka_app = self._create_kafka_app()

        # Topic 1: 座位初始化
        seat_init_topic = self.kafka_app.topic(
            name=KafkaTopicBuilder.seat_initialization_command_in_kvrocks(event_id=self.event_id),
            key_serializer='str',
            value_serializer='json',
        )

        # Topic 2: 預訂請求 (from booking service)
        reserving_topic = self.kafka_app.topic(
            name=KafkaTopicBuilder.ticket_reserving_request_to_reserved_in_kvrocks(
                event_id=self.event_id
            ),
            key_serializer='str',
            value_serializer='json',
        )

        # Topic 3: 釋放座位 (from event_ticketing service)
        release_topic = self.kafka_app.topic(
            name=KafkaTopicBuilder.release_ticket_status_to_available_in_kvrocks(
                event_id=self.event_id
            ),
            key_serializer='str',
            value_serializer='json',
        )

        # Topic 4: 完成支付 (from event_ticketing service)
        finalize_topic = self.kafka_app.topic(
            name=KafkaTopicBuilder.finalize_ticket_status_to_paid_in_kvrocks(
                event_id=self.event_id
            ),
            key_serializer='str',
            value_serializer='json',
        )

        # 設置無狀態處理 (stateful=False)
        self.kafka_app.dataframe(topic=seat_init_topic).apply(
            self._process_seat_initialization, stateful=False
        )

        self.kafka_app.dataframe(topic=reserving_topic).apply(
            self._process_reservation_request, stateful=False
        )

        self.kafka_app.dataframe(topic=release_topic).apply(
            self._process_release_seat, stateful=False
        )

        self.kafka_app.dataframe(topic=finalize_topic).apply(
            self._process_finalize_payment, stateful=False
        )

        Logger.base.info('✅ [SEAT-RESERVATION] All 4 topic streams configured (stateless)')

    def _parse_seat_id(self, seat_id: str) -> Optional[Dict]:
        """
        解析座位 ID

        Args:
            seat_id: 格式 "A-1-5-10" (section-subsection-row-seat_num)

        Returns:
            {'section': 'A', 'subsection': 1, 'row': 5, 'seat_num': 10}
            或 None (如果格式錯誤)
        """
        parts = seat_id.split('-')
        if len(parts) < 4:
            Logger.base.error(f'❌ [PARSE] Invalid seat_id format: {seat_id}')
            return None

        try:
            return {
                'section': parts[0],
                'subsection': int(parts[1]),
                'row': int(parts[2]),
                'seat_num': int(parts[3]),
            }
        except ValueError as e:
            Logger.base.error(f'❌ [PARSE] Failed to parse seat_id {seat_id}: {e}')
            return None

    def _extract_section_id(self, *, seat_id: str) -> str:
        """
        從 seat_id 提取 section_id
        例如: "A-1-1-1" -> "A-1"
        """
        parts = seat_id.split('-')
        if len(parts) >= 2:
            return f'{parts[0]}-{parts[1]}'
        return seat_id

    def _sync_to_kvrocks(self, seat_id: str, seat_state: dict, status_change: dict):
        """
        同步座位狀態到 Kvrocks（使用 Bitfield + Counter）

        同時處理：
        1. Bitfield 存儲座位狀態 (2 bits per seat)
        2. Counter 更新排/subsection 可售數
        3. 價格 Metadata 存儲
        4. Section 統計更新 (legacy, 用於 API)

        Args:
            seat_id: 座位 ID (e.g., "A-1-5-10")
            seat_state: 座位完整狀態
            status_change: {"from": "AVAILABLE", "to": "RESERVED"} or {"init": "AVAILABLE"}
        """
        try:
            # 解析座位 ID
            parsed = self._parse_seat_id(seat_id)
            if not parsed:
                return

            event_id = seat_state['event_id']
            status = seat_state['status']
            price = seat_state['price']

            # 使用同步版本的 Repository 更新 Bitfield + Counter
            seat_state_store.set_seat_status_sync(
                event_id=event_id,
                section=parsed['section'],
                subsection=parsed['subsection'],
                row=parsed['row'],
                seat_num=parsed['seat_num'],
                status=status,
                price=price,
            )

            # 更新 section 統計 (legacy, 用於 API 查詢)
            self._update_section_stats(seat_id, status_change)

            Logger.base.info(f'📊 [KVROCKS] Synced {seat_id} to Bitfield: {status}')

        except Exception as e:
            Logger.base.error(f'❌ [KVROCKS] Failed to sync {seat_id}: {e}')

    def _get_kvrocks_client(self) -> redis.Redis:
        """取得 Kvrocks 客戶端 (用於 legacy section stats)"""
        return redis.Redis(
            host=settings.KVROCKS_HOST,
            port=settings.KVROCKS_PORT,
            db=settings.KVROCKS_DB,
            password=settings.KVROCKS_PASSWORD if settings.KVROCKS_PASSWORD else None,
            decode_responses=True,
        )

    def _update_section_stats(self, seat_id: str, status_change: dict):
        """
        更新 section 統計 (legacy, 用於 API)

        維護 section_stats Hash 和 event_sections Sorted Set
        用於快速查詢整個 section 的統計資訊
        """
        try:
            client = self._get_kvrocks_client()
            section_id = self._extract_section_id(seat_id=seat_id)
            stats_key = f'section_stats:{self.event_id}:{section_id}'
            index_key = f'event_sections:{self.event_id}'

            if 'init' in status_change:
                # 初始化：增加 total 和 available
                client.hincrby(stats_key, 'total', 1)
                client.hincrby(stats_key, 'available', 1)
                client.zadd(index_key, {section_id: int(time.time())})
                client.expire(stats_key, SECTION_STATS_TTL)
                client.expire(index_key, SECTION_STATS_TTL)

            elif 'from' in status_change and 'to' in status_change:
                # 狀態轉換：更新計數器
                old_status = status_change['from'].lower()
                new_status = status_change['to'].lower()
                client.hincrby(stats_key, old_status, -1)
                client.hincrby(stats_key, new_status, 1)

            # 更新元數據
            client.hset(stats_key, 'section_id', section_id)
            client.hset(stats_key, 'event_id', str(self.event_id))
            client.hset(stats_key, 'updated_at', str(int(time.time())))

        except Exception as e:
            Logger.base.error(f'❌ [KVROCKS] Failed to update section stats: {e}')

    @Logger.io
    def _process_seat_initialization(self, message):
        """處理座位初始化 - 存儲到 Kvrocks"""
        seat_id = message['seat_id']
        seat_state = {
            'seat_id': seat_id,
            'event_id': message['event_id'],
            'status': 'AVAILABLE',
            'price': message['price'],
            'initialized_at': message.get('timestamp'),
            'booking_id': None,
            'buyer_id': None,
            'reserved_at': None,
            'sold_at': None,
        }

        # 同步到 Kvrocks (座位狀態 + 統計)
        self._sync_to_kvrocks(seat_id, seat_state, {'init': 'AVAILABLE'})

        Logger.base.info(f'✅ [SEAT-INIT] Initialized seat {seat_id}')
        return {'success': True, 'seat_id': seat_id}

    @Logger.io
    def _process_reservation_request(self, message):
        """處理預訂請求 - 執行座位選擇和預訂"""
        try:
            Logger.base.info(f'🎫 [RESERVATION] Processing request: {message}')

            # 使用 anyio 來運行異步 gateway
            result = anyio.from_thread.run(self.gateway.handle_event, event_data=message)

            Logger.base.info(f'✅ [RESERVATION] Request processed: {result}')
            return {'success': True, 'result': result}

        except Exception as e:
            Logger.base.error(f'❌ [RESERVATION] Failed to process: {e}')
            return {'success': False, 'error': str(e)}

    @Logger.io
    def _process_release_seat(self, message):
        """處理釋放座位 - 更新 Kvrocks 狀態"""
        seat_id = message.get('seat_id')
        if not seat_id:
            Logger.base.warning('⚠️ [RELEASE] Missing seat_id')
            return {'success': False, 'error': 'Missing seat_id'}

        # TODO(human): 從 Kvrocks 讀取當前座位狀態，驗證並更新
        # 提示：需要先讀取 seat:{seat_id}，檢查 status == 'RESERVED'，然後更新
        seat_state = {
            'seat_id': seat_id,
            'event_id': self.event_id,
            'status': 'AVAILABLE',
            'booking_id': None,
            'buyer_id': None,
            'reserved_at': None,
        }

        # 同步到 Kvrocks
        self._sync_to_kvrocks(seat_id, seat_state, {'from': 'RESERVED', 'to': 'AVAILABLE'})

        Logger.base.info(f'🔓 [RELEASE] Released seat {seat_id}')
        return {'success': True, 'seat_id': seat_id}

    @Logger.io
    def _process_finalize_payment(self, message):
        """
        處理完成支付 - 更新 Kvrocks 狀態

        從 legacy Hash 讀取當前狀態，驗證後更新到 Bitfield
        TODO: 未來可直接從 Bitfield 讀取，移除 Hash 依賴
        """
        seat_id = message.get('seat_id')
        if not seat_id:
            Logger.base.warning('⚠️ [FINALIZE] Missing seat_id')
            return {'success': False, 'error': 'Missing seat_id'}

        # 從 Kvrocks Hash 讀取當前狀態 (legacy)
        client = self._get_kvrocks_client()
        seat_key = f'seat:{seat_id}'
        current_state = client.hgetall(seat_key)

        if not current_state or current_state.get('status') != 'RESERVED':
            Logger.base.warning(f'⚠️ [FINALIZE] Seat {seat_id} not reserved or not found')
            return {'success': False, 'error': 'Seat not reserved'}

        # 更新狀態
        seat_state = {
            'seat_id': seat_id,
            'event_id': int(current_state.get('event_id', self.event_id)),
            'status': 'SOLD',
            'price': int(current_state.get('price', 0)),
            'initialized_at': current_state.get('initialized_at'),
            'booking_id': current_state.get('booking_id'),
            'buyer_id': current_state.get('buyer_id'),
            'reserved_at': current_state.get('reserved_at'),
            'sold_at': message.get('timestamp'),
        }

        # 同步到 Kvrocks Bitfield
        self._sync_to_kvrocks(seat_id, seat_state, {'from': 'RESERVED', 'to': 'SOLD'})

        Logger.base.info(f'💰 [FINALIZE] Finalized seat {seat_id}')
        return {'success': True, 'seat_id': seat_id}

    async def start(self):
        """啟動座位預訂服務"""
        try:
            # 使用 DI 容器創建 Gateway
            self.gateway = container.seat_reservation_gateway()

            # 設置 Kafka processing (無狀態)
            self._setup_kafka_processing()

            consumer_tag = f'[SEAT-RESERVATION-{self.instance_id}]'

            Logger.base.info(f'🪑 {consumer_tag} Starting seat reservation processor (Kvrocks)')
            Logger.base.info(f'📊 Event ID: {self.event_id}, Group: {self.consumer_group_id}')

            self.running = True

            # 啟動 Kafka processing
            if self.kafka_app:
                self.kafka_app.run()

        except Exception as e:
            Logger.base.error(f'❌ Seat reservation consumer failed: {e}')
            raise

    async def stop(self):
        """停止座位預訂服務"""
        if self.running:
            self.running = False

            if self.kafka_app:
                try:
                    Logger.base.info('🛑 Stopping Kafka application...')
                    self.kafka_app = None
                except Exception as e:
                    Logger.base.warning(f'⚠️ Error stopping Kafka app: {e}')

            Logger.base.info('🛑 Seat reservation consumer stopped')


def main():
    consumer = SeatReservationConsumer()
    try:
        asyncio.run(consumer.start())
    except KeyboardInterrupt:
        Logger.base.info('⚠️ Received interrupt signal')
        # 使用 asyncio.run 執行異步的 stop 方法
        asyncio.run(consumer.stop())
    except Exception as e:
        Logger.base.error(f'💥 Consumer error: {e}')
        # 即使發生錯誤也要嘗試清理資源
        try:
            asyncio.run(consumer.stop())
        except:
            pass
    finally:
        # 確保無論如何都會嘗試清理
        Logger.base.info('🧹 Cleaning up resources...')


if __name__ == '__main__':
    main()
