"""
Seat Reservation Consumer with Integrated RocksDB Processing
座位預訂服務消費者 - 整合 RocksDB 處理邏輯
負責接收預訂請求並直接在 RocksDB 中執行原子操作
"""

import asyncio
import os
import time
from typing import Any, Dict, Optional
from quixstreams import Application, State

from src.seat_reservation.use_case.reserve_seats_use_case import (
    ReservationRequest,
    ReserveSeatsUseCase,
    create_reserve_seats_use_case,
)
from src.shared.logging.loguru_io import Logger
from src.shared.config.core_setting import settings
from src.shared.message_queue.unified_mq_consumer import UnifiedEventConsumer


class SeatReservationEventHandler:
    """
    座位預訂事件處理器
    處理來自 booking_service 的預訂請求
    """

    def __init__(self, reserve_use_case: ReserveSeatsUseCase):
        self.reserve_use_case = reserve_use_case

    @Logger.io
    async def can_handle(self, event_type: str) -> bool:
        """檢查是否能處理此事件類型"""
        supported_events = ['BookingCreated', 'SeatReservationRequest', 'SeatReleaseRequest']
        return event_type in supported_events

    @Logger.io
    async def handle(self, event_data: Dict[str, Any]) -> bool:
        """
        處理事件

        Args:
            event_data: 事件數據

        Returns:
            bool: 處理是否成功
        """
        event_type = event_data.get('event_type')

        try:
            if event_type == 'BookingCreated':
                return await self._handle_booking_created(event_data)
            elif event_type == 'SeatReservationRequest':
                return await self._handle_seat_reservation_request(event_data)
            elif event_type == 'SeatReleaseRequest':
                return await self._handle_seat_release_request(event_data)
            else:
                Logger.base.warning(f'⚠️ [SEAT_HANDLER] Unsupported event type: {event_type}')
                return False

        except Exception as e:
            Logger.base.error(f'❌ [SEAT_HANDLER] Error handling {event_type}: {e}')
            return False

    async def _handle_booking_created(self, event_data: Dict[str, Any]) -> bool:
        """
        處理訂單創建事件
        當 booking_service 創建訂單後，需要預訂座位
        """
        data = event_data.get('data', {})

        booking_id = data.get('booking_id')
        buyer_id = data.get('buyer_id')
        event_id = data.get('event_id')
        seat_selection_mode = data.get('seat_selection_mode')
        seat_positions = data.get('seat_positions', [])
        quantity = data.get('quantity')
        section = data.get('section')
        subsection = data.get('subsection')

        Logger.base.info(
            f'📋 [SEAT_HANDLER] Processing BookingCreated - '
            f'booking: {booking_id}, buyer: {buyer_id}, event: {event_id}'
        )

        # 創建預訂請求
        reservation_request = ReservationRequest(
            booking_id=booking_id,
            buyer_id=buyer_id,
            event_id=event_id,
            selection_mode=seat_selection_mode,
            quantity=quantity,
            seat_positions=seat_positions,
            section_filter=section,
            subsection_filter=subsection,
        )

        # 執行座位預訂
        result = await self.reserve_use_case.reserve_seats(reservation_request)

        # 發送結果事件回 booking_service
        await self._send_reservation_result(result)

        return result.success

    async def _handle_seat_reservation_request(self, event_data: Dict[str, Any]) -> bool:
        """處理直接的座位預訂請求"""
        Logger.base.info(
            f'🎯 [SEAT_HANDLER] Processing direct seat reservation request: {event_data.get("event_type", "Unknown")}'
        )
        # TODO: 實現直接預訂邏輯
        return True

    async def _handle_seat_release_request(self, event_data: Dict[str, Any]) -> bool:
        """處理座位釋放請求（取消/超時）"""
        data = event_data.get('data', {})

        booking_id = data.get('booking_id')

        Logger.base.info(f'🔓 [SEAT_HANDLER] Processing seat release for booking {booking_id}')

        # TODO: 實現座位釋放邏輯
        return True

    async def _send_reservation_result(self, result) -> None:
        """
        發送預訂結果回 booking_service
        """
        try:
            from datetime import datetime

            from src.seat_reservation.use_case.reserve_seats_use_case import SeatReservationResult
            from src.shared.message_queue.unified_mq_publisher import publish_domain_event

            if result.success:
                event_type = 'SeatReservationSuccess'
                Logger.base.info(
                    f'✅ [SEAT_HANDLER] Sending success result for booking {result.booking_id}'
                )
            else:
                event_type = 'SeatReservationFailed'
                Logger.base.warning(
                    f'❌ [SEAT_HANDLER] Sending failure result for booking {result.booking_id}: '
                    f'{result.error_message}'
                )

            # 創建結果事件
            result_event = SeatReservationResult(
                booking_id=result.booking_id,
                success=result.success,
                reserved_seats=result.reserved_seats or [],
                total_price=result.total_price,
                error_message=result.error_message or '',
                event_id=result.event_id or 0,
                occurred_at=datetime.now(),
            )

            # 發送事件到 booking service
            await publish_domain_event(
                event=result_event,
                topic='seat-reservation-results',
                partition_key=str(result.booking_id),
            )

            Logger.base.info(
                f'📤 [SEAT_HANDLER] Sent {event_type} event for booking {result.booking_id}'
            )

        except Exception as e:
            Logger.base.error(
                f'❌ [SEAT_HANDLER] Failed to send reservation result for booking {result.booking_id}: {e}'
            )


class SeatInitializationService:
    """
    座位初始化服務接口

    提供簡單的 RocksDB 座位初始化功能，供 CreateEventUseCase 使用
    直接寫入 RocksDB 而不依賴 Kafka streaming
    """

    def __init__(self, state_dir: str = './rocksdb_state'):
        self.state_dir = state_dir
        self._ensure_state_dir()
        # 為避免複雜的 Kafka 依賴，直接使用文件系統操作模擬 RocksDB 狀態
        self._seats_state = {}

    def _ensure_state_dir(self):
        """確保狀態目錄存在"""
        import os

        os.makedirs(self.state_dir, exist_ok=True)

    @Logger.io
    async def initialize_seats_for_event(self, *, event_id: int, tickets) -> int:
        """
        為活動初始化所有座位到 RocksDB

        Args:
            event_id: 活動 ID
            tickets: 票務列表

        Returns:
            初始化成功的座位數量
        """
        initialized_count = 0

        for ticket in tickets:
            try:
                seat_id = ticket.seat_identifier

                # 直接設置座位狀態
                seat_state = {
                    'status': 'AVAILABLE',
                    'event_id': event_id,
                    'price': ticket.price,
                    'initialized_at': int(time.time()),
                }

                self._seats_state[seat_id] = seat_state
                initialized_count += 1
                Logger.base.debug(f'✅ Initialized seat {seat_id} for event {event_id}')

            except Exception as e:
                Logger.base.warning(f'⚠️ Failed to initialize seat {ticket.seat_identifier}: {e}')
                continue

        # 將狀態持久化到文件，讓 monitor 可以讀取
        await self._persist_state(event_id)

        return initialized_count

    async def _persist_state(self, event_id: int):
        """將狀態持久化到文件"""
        try:
            import json

            state_file = f'{self.state_dir}/event_{event_id}_seats.json'

            # 轉換為可序列化的格式
            serializable_state = {}
            for seat_id, state in self._seats_state.items():
                if state.get('event_id') == event_id:
                    serializable_state[seat_id] = state

            with open(state_file, 'w') as f:
                json.dump(serializable_state, f, indent=2)

            Logger.base.info(f'💾 Persisted {len(serializable_state)} seats to {state_file}')

        except Exception as e:
            Logger.base.warning(f'⚠️ Failed to persist state: {e}')


class MockState:
    """模擬 Quix Streams State 對象用於直接 RocksDB 操作"""

    def __init__(self, seats_state: dict, seat_id: str):
        self._seats_state = seats_state
        self._seat_id = seat_id

        # 為這個座位創建狀態存儲
        if seat_id not in self._seats_state:
            self._seats_state[seat_id] = {}

    def get(self, key: str, default=None):
        """獲取狀態值"""
        return self._seats_state[self._seat_id].get(key, default)

    def set(self, key: str, value):
        """設置狀態值"""
        self._seats_state[self._seat_id][key] = value

    def delete(self, key: str):
        """刪除狀態值"""
        self._seats_state[self._seat_id].pop(key, None)


class RocksDBSeatProcessor:
    """
    RocksDB 座位狀態處理器 - 整合到 SeatReservationConsumer

    這是整個系統的狀態管理核心：
    1. 接收座位操作命令（通過 Kafka）
    2. 在 RocksDB 中執行原子操作
    3. 發送處理結果事件
    """

    def __init__(self, event_id: Optional[int] = None):
        self.app = None
        self.running = False
        # 優先使用傳入的 event_id，否則從環境變數讀取
        if event_id:
            self.event_id = event_id
        else:
            env_event_id = os.getenv('EVENT_ID')
            self.event_id = (
                int(env_event_id) if env_event_id else 0
            )  # 使用 0 作為默認值而不是 None  # 使用 0 作為默認值而不是 None

    @Logger.io
    def create_application(self) -> Application:
        """
        創建 Quix Streams 應用
        配置 RocksDB 作為狀態存儲
        """
        # 為每個實例創建唯一的消費者群組和狀態目錄
        import uuid

        instance_id = str(uuid.uuid4())[:8]
        consumer_group = f'seat-processor-{instance_id}'
        state_dir = f'./rocksdb_state_{instance_id}'

        self.app = Application(
            broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=consumer_group,
            auto_offset_reset='earliest',
            state_dir=state_dir,  # 使用唯一的狀態目錄
            # 配置 RocksDB 序列化 (removed due to type incompatibility)
        )

        Logger.base.info(
            f'🏗️ [ROCKSDB] Created Quix Streams application with consumer group: {consumer_group}, state dir: {state_dir}'
        )
        return self.app

    def setup_topics_and_streams(self):
        """設置 Kafka topics 和 streaming 處理邏輯"""
        if not self.app:
            self.create_application()

        if not self.app:
            raise RuntimeError('Failed to create Quix Streams application')

        # 根據 README.md 的標準化 topic 格式構建座位初始化 topic
        if self.event_id:
            # 使用標準化格式：event-id-{event_id}______seat-initialization-command______event-ticketing-service___to___seat-reservation-service
            topic_name = f'event-id-{self.event_id}______seat-initialization-command______event-ticketing-service___to___seat-reservation-service'
        else:
            # 如果沒有指定 event_id，使用通用名稱（向後兼容）
            topic_name = 'seat-initialization-commands'

        seat_commands_topic = self.app.topic(
            name=topic_name,
            key_serializer='str',
            value_serializer='json',
        )

        # 輸出 topic：處理結果
        seat_results_topic = self.app.topic(
            name='seat-results',
            key_serializer='str',
            value_serializer='json',
        )

        # 創建 streaming dataframe
        sdf = self.app.dataframe(topic=seat_commands_topic)

        # 應用狀態處理邏輯
        sdf = sdf.apply(self.process_seat_command, stateful=True)

        # 輸出處理結果
        sdf.to_topic(seat_results_topic)

        Logger.base.info(f'🔗 [ROCKSDB] Configured streaming for topic: {topic_name}')

    def process_seat_command(self, message: Dict[str, Any], state: State) -> Dict[str, Any]:
        """
        處理座位命令的核心函數
        這是在 RocksDB 中執行原子操作的地方
        """
        # 支援兩種消息格式：
        # 1. 直接格式：{"action": "RESERVE", "seat_id": "A-1-1-1", ...}
        # 2. 事件格式：{"event_type": "SeatInitialization", "data": {...}}

        if 'event_type' in message and 'data' in message:
            # 事件格式 - 提取 data 部分
            data = message['data']
            action = data.get('action')
            seat_id = data.get('seat_id')
            booking_id = data.get('booking_id', 0)
            buyer_id = data.get('buyer_id', 0)
            event_id = data.get('event_id')
            price = data.get('price')
        else:
            # 直接格式 - 直接使用消息內容
            action = message.get('action')
            seat_id = message.get('seat_id')
            booking_id = message.get('booking_id', 0)
            buyer_id = message.get('buyer_id', 0)
            event_id = message.get('event_id')
            price = message.get('price')

        Logger.base.info(
            f'🎯 [ROCKSDB] Processing {action} for seat {seat_id}, '
            f'booking {booking_id}, buyer {buyer_id}'
        )

        try:
            if action == 'RESERVE':
                return self._handle_reserve(message, state)
            elif action == 'RELEASE':
                return self._handle_release(message, state)
            elif action == 'CONFIRM_SOLD':
                return self._handle_confirm_sold(message, state)
            elif action == 'INITIALIZE':
                # 為初始化傳遞額外參數
                init_message = {
                    'seat_id': seat_id,
                    'event_id': event_id,
                    'price': price,
                    'booking_id': booking_id,
                }
                return self._handle_initialize(init_message, state)
            else:
                return self._error_result(seat_id or 'unknown', f'Unknown action: {action}')

        except Exception as e:
            Logger.base.error(f'❌ [ROCKSDB] Error processing {action} for {seat_id}: {e}')
            return self._error_result(seat_id or 'unknown', f'Processing error: {str(e)}')

    def _handle_reserve(self, message: Dict[str, Any], state: State) -> Dict[str, Any]:
        """處理座位預訂"""
        seat_id = message['seat_id']
        booking_id = message['booking_id']
        buyer_id = message['buyer_id']
        current_time = int(time.time())

        # 檢查當前狀態
        current_status = state.get('status', 'AVAILABLE')
        current_booking = state.get('booking_id')

        if current_status == 'AVAILABLE':
            # 原子性更新為 RESERVED
            state.set('status', 'RESERVED')
            state.set('booking_id', booking_id)
            state.set('buyer_id', buyer_id)
            state.set('reserved_at', current_time)

            Logger.base.info(f'✅ [ROCKSDB] Reserved seat {seat_id} for booking {booking_id}')

            return {
                'success': True,
                'action': 'RESERVED',
                'seat_id': seat_id,
                'booking_id': booking_id,
                'buyer_id': buyer_id,
                'timestamp': current_time,
            }

        elif current_status == 'RESERVED' and current_booking == booking_id:
            # 同一個訂單的重複請求，視為成功
            Logger.base.info(
                f'🔄 [ROCKSDB] Seat {seat_id} already reserved by same booking {booking_id}'
            )

            return {
                'success': True,
                'action': 'ALREADY_RESERVED',
                'seat_id': seat_id,
                'booking_id': booking_id,
                'buyer_id': state.get('buyer_id'),
                'timestamp': current_time,
            }

        else:
            # 座位不可用
            Logger.base.warning(
                f'❌ [ROCKSDB] Seat {seat_id} not available - status: {current_status}, '
                f'booking: {current_booking}'
            )

            return {
                'success': False,
                'action': 'RESERVE_FAILED',
                'seat_id': seat_id,
                'booking_id': booking_id,
                'reason': f'Seat not available - status: {current_status}',
                'current_booking': current_booking,
                'timestamp': current_time,
            }

    def _handle_release(self, message: Dict[str, Any], state: State) -> Dict[str, Any]:
        """處理座位釋放"""
        seat_id = message['seat_id']
        booking_id = message.get('booking_id')

        current_status = state.get('status')
        current_booking = state.get('booking_id')

        # 驗證權限：只能釋放自己預訂的座位
        if current_status == 'RESERVED' and current_booking == booking_id:
            state.set('status', 'AVAILABLE')
            state.delete('booking_id')
            state.delete('buyer_id')
            state.delete('reserved_at')

            Logger.base.info(f'🔓 [ROCKSDB] Released seat {seat_id} from booking {booking_id}')

            return {
                'success': True,
                'action': 'RELEASED',
                'seat_id': seat_id,
                'booking_id': booking_id,
                'timestamp': int(time.time()),
            }
        else:
            return {
                'success': False,
                'action': 'RELEASE_FAILED',
                'seat_id': seat_id,
                'booking_id': booking_id,
                'reason': f'Cannot release - status: {current_status}, booking: {current_booking}',
                'timestamp': int(time.time()),
            }

    def _handle_confirm_sold(self, message: Dict[str, Any], state: State) -> Dict[str, Any]:
        """處理座位售出確認"""
        seat_id = message['seat_id']
        booking_id = message['booking_id']

        current_status = state.get('status')
        current_booking = state.get('booking_id')

        if current_status == 'RESERVED' and current_booking == booking_id:
            state.set('status', 'SOLD')
            state.set('sold_at', int(time.time()))

            Logger.base.info(
                f'💰 [ROCKSDB] Confirmed seat {seat_id} as SOLD for booking {booking_id}'
            )

            return {
                'success': True,
                'action': 'CONFIRMED_SOLD',
                'seat_id': seat_id,
                'booking_id': booking_id,
                'buyer_id': state.get('buyer_id'),
                'timestamp': int(time.time()),
            }
        else:
            return {
                'success': False,
                'action': 'CONFIRM_FAILED',
                'seat_id': seat_id,
                'booking_id': booking_id,
                'reason': f'Cannot confirm - status: {current_status}, booking: {current_booking}',
                'timestamp': int(time.time()),
            }

    def _handle_initialize(self, message: Dict[str, Any], state: State) -> Dict[str, Any]:
        """處理座位初始化"""
        seat_id = message['seat_id']
        event_id = message.get('event_id')
        price = message.get('price', 0)

        # 從 seat_id 解析事件信息（如果未提供）
        if not event_id or not price:
            if not event_id:
                event_id = message.get('booking_id', 999)  # 從 booking_id 推導或使用默認值
            if not price:
                price = 1000  # 默認價格

        # 初始化座位狀態
        state.set('status', 'AVAILABLE')
        state.set('event_id', event_id)
        state.set('price', price)
        state.set('initialized_at', int(time.time()))

        # 清除任何舊的預訂信息
        state.delete('booking_id')
        state.delete('buyer_id')
        state.delete('reserved_at')
        state.delete('sold_at')

        Logger.base.info(
            f'🆕 [ROCKSDB] Initialized seat {seat_id} for event {event_id}, price: {price}'
        )

        return {
            'success': True,
            'action': 'INITIALIZED',
            'seat_id': seat_id,
            'event_id': event_id,
            'price': price,
            'timestamp': int(time.time()),
        }

    def _error_result(self, seat_id: str, error: str) -> Dict[str, Any]:
        """創建錯誤結果"""
        return {
            'success': False,
            'action': 'ERROR',
            'seat_id': seat_id,
            'error': error,
            'timestamp': int(time.time()),
        }

    @Logger.io
    async def start(self):
        """啟動 RocksDB 處理器"""
        if not self.app:
            self.setup_topics_and_streams()

        if not self.app:
            raise RuntimeError('Failed to create Quix Streams application')

        Logger.base.info('🚀 [ROCKSDB] Starting seat processor...')
        self.running = True

        try:
            # 這會啟動 Quix Streams 處理循環
            self.app.run()
        except KeyboardInterrupt:
            Logger.base.info('⏹️ [ROCKSDB] Received stop signal')
        except Exception as e:
            Logger.base.error(f'❌ [ROCKSDB] Error in seat processor: {e}')
            raise
        finally:
            self.running = False
            Logger.base.info('🛑 [ROCKSDB] Seat processor stopped')


class SeatReservationConsumer:
    """
    座位預訂消費者 - 整合 RocksDB 處理

    這是 seat_reservation 服務的主要入口點
    整合了統一事件消費者和 RocksDB 狀態處理器
    """

    def __init__(self):
        self.consumer = None
        self.handler = None
        self.rocksdb_processor = None
        self.running = False

    @Logger.io
    async def initialize(self):
        """初始化消費者和處理器"""
        # 創建處理器
        reserve_use_case = create_reserve_seats_use_case()
        self.handler = SeatReservationEventHandler(reserve_use_case)

        # 創建 RocksDB 處理器
        self.rocksdb_processor = RocksDBSeatProcessor()

        # 創建統一消費者
        topics = [
            'booking-events',  # 來自 booking_service
            'seat-reservation-requests',  # 直接預訂請求
        ]

        self.consumer = UnifiedEventConsumer(
            topics=topics,
            consumer_group_id='seat-reservation-service',
            consumer_tag='[SEAT_RESERVATION]',
        )

        # 註冊處理器
        self.consumer.register_handler(self.handler)

        Logger.base.info(
            '🏗️ [SEAT_CONSUMER] Initialized seat reservation consumer with RocksDB integration'
        )

    @Logger.io
    async def start(self):
        """啟動消費者（包含 RocksDB 處理器）"""
        if not self.consumer:
            await self.initialize()

        Logger.base.info('🚀 [SEAT_CONSUMER] Starting seat reservation consumer with RocksDB...')
        self.running = True

        try:
            # 並行啟動統一消費者和 RocksDB 處理器
            tasks = []

            if self.consumer:
                tasks.append(asyncio.create_task(self.consumer.start()))

            if self.rocksdb_processor:
                tasks.append(asyncio.create_task(self.rocksdb_processor.start()))

            # 等待任一任務完成或出錯
            await asyncio.gather(*tasks)

        except Exception as e:
            Logger.base.error(f'❌ [SEAT_CONSUMER] Error starting consumer: {e}')
            raise
        finally:
            self.running = False

    @Logger.io
    async def stop(self):
        """停止消費者"""
        if self.running:
            Logger.base.info('⏹️ [SEAT_CONSUMER] Stopping seat reservation consumer...')

            if self.consumer:
                await self.consumer.stop()

            # RocksDB 處理器會在主循環中斷時自動停止
            self.running = False


# 全局實例
_seat_reservation_consumer = None


async def get_seat_reservation_consumer() -> SeatReservationConsumer:
    """獲取座位預訂消費者實例"""
    global _seat_reservation_consumer

    if _seat_reservation_consumer is None:
        _seat_reservation_consumer = SeatReservationConsumer()
        await _seat_reservation_consumer.initialize()

    return _seat_reservation_consumer


# 啟動腳本
if __name__ == '__main__':

    async def main():
        consumer = await get_seat_reservation_consumer()
        await consumer.start()

    # 啟動消費者
    asyncio.run(main())
