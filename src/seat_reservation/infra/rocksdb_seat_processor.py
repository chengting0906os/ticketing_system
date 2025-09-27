"""
RocksDB Seat Processor
基於 Quix Streams 的 RocksDB 座位狀態處理器
"""

import time
import orjson
from typing import Dict, Any
from quixstreams import Application, State

from src.shared.logging.loguru_io import Logger
from src.shared.config.core_setting import settings


class RocksDBSeatProcessor:
    """
    RocksDB 座位狀態處理器

    這是整個系統的狀態管理核心：
    1. 接收座位操作命令（通過 Kafka）
    2. 在 RocksDB 中執行原子操作
    3. 發送處理結果事件
    """

    def __init__(self):
        self.app = None
        self.running = False

    @Logger.io
    def create_application(self) -> Application:
        """
        創建 Quix Streams 應用

        配置 RocksDB 作為狀態存儲
        """
        self.app = Application(
            broker_address=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group='seat-processor',
            auto_offset_reset='earliest',
            state_dir='./rocksdb_state',  # RocksDB 存儲目錄
            # 配置 RocksDB 序列化
            rocksdb_options={'dumps': orjson.dumps, 'loads': orjson.loads},
        )

        Logger.base.info('🏗️ [ROCKSDB] Created Quix Streams application with RocksDB state')
        return self.app

    def setup_topics_and_streams(self):
        """
        設置 Kafka topics 和 streaming 處理邏輯
        """
        if not self.app:
            self.create_application()

        # 輸入 topic：座位命令
        seat_commands_topic = self.app.topic(
            name='seat-commands',
            key_serializer='str',  # 座位ID作為key確保路由到正確分區
            value_serializer='json',  # 使用內置的json序列化器
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

        Logger.base.info('🔗 [ROCKSDB] Configured streaming topics and processing logic')

    @Logger.io
    async def start(self):
        """啟動 RocksDB 處理器"""
        if not self.app:
            self.setup_topics_and_streams()

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

    def process_seat_command(self, message: Dict[str, Any], state: State) -> Dict[str, Any]:
        """
        處理座位命令的核心函數

        這是在 RocksDB 中執行原子操作的地方

        Args:
            message: 座位命令消息
            state: Quix Streams 提供的 RocksDB 狀態對象

        Returns:
            處理結果
        """
        # 支持兩種消息格式：
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
            # seat_id 格式: "section-subsection-row-seat"
            # 這裡我們需要從某處獲取 event_id 和 price
            # 暫時使用默認值，實際使用時需要改進
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


# 工廠函數
def create_rocksdb_processor() -> RocksDBSeatProcessor:
    """創建 RocksDB 處理器實例"""
    return RocksDBSeatProcessor()


# 啟動腳本
if __name__ == '__main__':
    processor = create_rocksdb_processor()
    processor.setup_topics_and_streams()

    import asyncio

    asyncio.run(processor.start())
