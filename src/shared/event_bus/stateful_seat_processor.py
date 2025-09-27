"""
Stateful Seat Processor using Quix Streams + RocksDB
實現無鎖座位預訂的核心邏輯
"""

import time
import orjson
from typing import Dict, List, Optional, Any
from quixstreams import Application, State
from src.shared.logging.loguru_io import Logger
from src.booking.port.seat_state_manager import SeatStateManager, SeatReservation


class RocksDBSeatStateManager(SeatStateManager):
    """
    基於 Quix Streams RocksDB 的座位狀態管理器

    核心特性：
    1. 利用 Kafka partition 保證同一座位的請求順序處理
    2. 使用 RocksDB State 實現原子操作
    3. 無需分散式鎖
    """

    def __init__(self, app: Application):
        self.app = app
        self.reservation_timeout = 300  # 5分鐘預訂超時

    @Logger.io
    async def reserve_seats_atomic(self, seat_ids: List[str], buyer_id: int) -> Dict[str, bool]:
        """
        原子性預訂多個座位

        重要：這個方法應該在 Quix Streams 的處理函數內調用
        以確保能訪問到正確的 State
        """
        results = {}

        for seat_id in seat_ids:
            # 每個座位作為獨立的消息發送
            # 使用座位ID作為 key 確保路由到正確的 partition
            success = await self._reserve_single_seat(seat_id, buyer_id)
            results[seat_id] = success

        return results

    async def _reserve_single_seat(self, seat_id: str, buyer_id: int) -> bool:
        """
        預訂單個座位

        注意：實際實現需要在 Quix Streams 處理函數中
        這裡只是接口定義
        """
        # 實際邏輯會在 process_seat_reservation 中實現
        # 這裡先返回占位結果
        return True

    @Logger.io
    async def release_seats(self, seat_ids: List[str]) -> None:
        """釋放座位"""
        for seat_id in seat_ids:
            # 發送釋放事件到對應的 partition
            await self._send_release_event(seat_id)

    async def _send_release_event(self, seat_id: str) -> None:
        """發送座位釋放事件"""
        # TODO: 實現發送邏輯
        pass

    @Logger.io
    async def confirm_seats_sold(self, seat_ids: List[str]) -> None:
        """確認座位售出"""
        for seat_id in seat_ids:
            # 發送確認售出事件
            await self._send_confirm_sold_event(seat_id)

    async def _send_confirm_sold_event(self, seat_id: str) -> None:
        """發送座位售出確認事件"""
        # TODO: 實現發送邏輯
        pass

    @Logger.io
    async def get_seat_status(self, seat_id: str) -> Optional[SeatReservation]:
        """查詢座位狀態"""
        # TODO: 實現查詢邏輯
        return None


def create_seat_processor_app() -> Application:
    """
    創建座位處理應用

    這是真正處理座位狀態的 Quix Streams 應用
    """
    app = Application(
        broker_address='localhost:9092',
        consumer_group='seat-processor',
        auto_offset_reset='earliest',
        rocksdb_options={'dumps': orjson.dumps, 'loads': orjson.loads},
    )

    # 創建座位預訂 topic
    seat_topic = app.topic(
        name='seat-reservations',
        key_serializer='str',  # 座位ID作為key
        value_serializer='json',
    )

    # 創建 streaming dataframe
    sdf = app.dataframe(topic=seat_topic)

    # 應用狀態處理邏輯
    sdf = sdf.apply(process_seat_reservation, stateful=True)

    # 輸出處理結果
    output_topic = app.topic(name='seat-reservation-results', value_serializer='json')
    sdf.to_topic(output_topic)

    return app


def process_seat_reservation(message: Dict[str, Any], state: State) -> Dict[str, Any]:
    """
    處理座位預訂請求（無鎖原子操作）

    這是核心的狀態處理函數，在 RocksDB 中原子性地更新座位狀態

    Args:
        message: 包含 action, seat_id, buyer_id 等信息
        state: Quix Streams 提供的狀態對象（backed by RocksDB）

    Returns:
        處理結果
    """
    action = message.get('action')
    seat_id = message.get('seat_id')
    buyer_id = message.get('buyer_id')

    Logger.base.info(f'🎯 [SEAT] Processing {action} for seat {seat_id}')

    if action == 'RESERVE':
        # 檢查當前狀態
        current_status = state.get('status', 'AVAILABLE')

        if current_status == 'AVAILABLE':
            # 原子性更新為 RESERVED
            state.set('status', 'RESERVED')
            state.set('buyer_id', buyer_id)
            state.set('reserved_at', int(time.time()))

            Logger.base.info(f'✅ [SEAT] Reserved seat {seat_id} for buyer {buyer_id}')

            return {
                'success': True,
                'seat_id': seat_id,
                'buyer_id': buyer_id,
                'status': 'RESERVED',
                'timestamp': int(time.time()),
            }
        else:
            Logger.base.warning(f'❌ [SEAT] Seat {seat_id} already {current_status}')

            return {
                'success': False,
                'seat_id': seat_id,
                'reason': f'Seat already {current_status}',
                'current_buyer': state.get('buyer_id'),
            }

    elif action == 'RELEASE':
        # 釋放座位
        state.set('status', 'AVAILABLE')
        state.delete('buyer_id')
        state.delete('reserved_at')

        Logger.base.info(f'🔓 [SEAT] Released seat {seat_id}')

        return {'success': True, 'seat_id': seat_id, 'status': 'AVAILABLE', 'action': 'RELEASED'}

    elif action == 'CONFIRM_SOLD':
        # 確認售出
        current_status = state.get('status')

        if current_status == 'RESERVED':
            state.set('status', 'SOLD')
            state.set('sold_at', int(time.time()))

            Logger.base.info(f'💰 [SEAT] Confirmed seat {seat_id} as SOLD')

            return {
                'success': True,
                'seat_id': seat_id,
                'status': 'SOLD',
                'buyer_id': state.get('buyer_id'),
            }
        else:
            return {
                'success': False,
                'seat_id': seat_id,
                'reason': f'Cannot sell seat in {current_status} status',
            }

    elif action == 'CHECK_EXPIRED':
        # 檢查並清理過期預訂
        reserved_at = state.get('reserved_at')
        if reserved_at:
            if (time.time() - reserved_at) > 300:  # 5分鐘超時
                state.set('status', 'AVAILABLE')
                state.delete('buyer_id')
                state.delete('reserved_at')

                Logger.base.info(f'⏰ [SEAT] Expired reservation for seat {seat_id}')

                return {
                    'success': True,
                    'seat_id': seat_id,
                    'action': 'EXPIRED',
                    'status': 'AVAILABLE',
                }

        return {'success': False, 'reason': 'Not expired'}

    else:
        return {'success': False, 'reason': f'Unknown action: {action}'}


# 使用範例
if __name__ == '__main__':
    app = create_seat_processor_app()
    app.run()
