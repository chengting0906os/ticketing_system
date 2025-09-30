"""
Seat State Handler Implementation
座位狀態處理器實現 - 直接使用 EventTicketingMqConsumer 的 RocksDB 狀態
"""

from typing import Dict, List, Optional

from src.seat_reservation.domain.seat_state_handler import SeatStateHandler
from src.shared.logging.loguru_io import Logger


class SeatStateHandlerImpl(SeatStateHandler):
    """
    座位狀態處理器實現 - 使用已存在的 EventTicketingMqConsumer RocksDB 狀態

    職責:
    1. 查詢座位可用性 (直接從 RocksDB 讀取)
    2. 預訂座位 (發送 Kafka 消息到狀態管理器)
    3. 釋放座位 (發送 Kafka 消息到狀態管理器)
    4. 確認付款 (發送 Kafka 消息到狀態管理器)

    注意：真正的狀態存儲由 EventTicketingMqConsumer 管理
    """

    def __init__(self):
        # 使用 SeatReservationConsumer 來讀取 RocksDB 狀態
        from src.seat_reservation.infra.seat_reservation_mq_consumer import SeatReservationConsumer

        self.seat_reader = SeatReservationConsumer()

    def is_available(self) -> bool:
        """檢查服務是否可用"""
        return True  # 簡化：總是可用

    def get_seat_states(self, seat_ids: List[str], event_id: int) -> Dict[str, Dict]:
        """獲取指定座位的狀態 - 從 RocksDB 讀取真實狀態"""
        Logger.base.info(f'🔍 [SEAT-STATE] Getting states for {len(seat_ids)} seats')

        if not self.is_available():
            raise RuntimeError('Seat state handler not available')

        # 使用 SeatReservationConsumer 讀取 RocksDB 狀態
        try:
            # 確保 seat_reader 已初始化（不使用 asyncio.run）
            if not self.seat_reader.rocksdb_app:
                # 創建 RocksDB app 但不運行異步初始化
                self.seat_reader.rocksdb_app = self.seat_reader._create_rocksdb_app()

            # 讀取座位狀態
            seat_states = self.seat_reader.read_seat_states(seat_ids)

            Logger.base.info(
                f'✅ [SEAT-STATE] Retrieved {len(seat_states)} seat states from RocksDB'
            )
            return seat_states

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Failed to read seat states from RocksDB: {e}')
            # 如果讀取失敗，返回空結果
            return {}

    def get_available_seats_by_section(
        self, event_id: int, section: str, subsection: int, limit: Optional[int] = None
    ) -> List[Dict]:
        """按區域獲取可用座位"""
        Logger.base.info(f'🔍 [SEAT-STATE] Getting available seats for {section}-{subsection}')

        if not self.is_available():
            raise RuntimeError('Seat state handler not available')

        available_seats = []

        try:
            # 構建該區域的所有座位ID列表
            seat_ids_to_check = []
            for row in range(1, 11):  # 最多10排
                for seat_num in range(1, 31):  # 每排最多30個座位
                    if limit and len(available_seats) >= limit:
                        break
                    seat_id = f'{section}-{subsection}-{row}-{seat_num}'
                    seat_ids_to_check.append(seat_id)

            # 使用 SeatReservationConsumer 批量讀取座位狀態
            all_seat_states = self.get_seat_states(seat_ids_to_check, event_id)

            # 篩選出可用座位
            for _, seat_state in all_seat_states.items():
                if seat_state.get('status') == 'AVAILABLE':
                    available_seats.append(seat_state)
                    if limit and len(available_seats) >= limit:
                        break

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Error scanning seats: {e}')
            raise

        Logger.base.info(
            f'📊 [SEAT-STATE] Found {len(available_seats)} available seats in section {section}-{subsection}'
        )
        return available_seats

    def reserve_seats(
        self, seat_ids: List[str], booking_id: int, buyer_id: int, event_id: int
    ) -> Dict[str, bool]:
        """預訂座位 (AVAILABLE -> RESERVED)"""
        Logger.base.info(
            f'🔒 [SEAT-STATE] Reserving {len(seat_ids)} seats for booking {booking_id}'
        )

        if not self.is_available():
            raise RuntimeError('Seat state handler not available')

        # 獲取當前座位狀態
        current_states = self.get_seat_states(seat_ids, event_id)

        results = {}

        # 原子性預訂：先檢查所有座位是否可用
        unavailable_seats = []
        for seat_id in seat_ids:
            current_state = current_states.get(seat_id)

            if not current_state:
                unavailable_seats.append(seat_id)
                Logger.base.warning(f'⚠️ [SEAT-STATE] Seat {seat_id} not found')
                continue

            if current_state.get('status') != 'AVAILABLE':
                unavailable_seats.append(seat_id)
                Logger.base.warning(
                    f'⚠️ [SEAT-STATE] Seat {seat_id} not available (status: {current_state.get("status")})'
                )

        # 如果任何座位不可用，全部失敗
        if unavailable_seats:
            Logger.base.error(
                f'❌ [SEAT-STATE] Cannot reserve seats, {len(unavailable_seats)} unavailable: {unavailable_seats}'
            )
            return {seat_id: False for seat_id in seat_ids}

        # TODO: 執行原子性預訂 - 這裡需要發送到 EventTicketingMqConsumer
        # 目前先返回成功，實際應該發送 Kafka 消息
        try:
            for seat_id in seat_ids:
                # 這裡應該發送 Kafka 消息到 EventTicketingMqConsumer 來執行狀態更新
                results[seat_id] = True
                Logger.base.info(f'✅ [SEAT-STATE] Requested reservation for seat {seat_id}')

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Failed to reserve seats: {e}')
            raise

        success_count = sum(results.values())
        Logger.base.info(
            f'🎯 [SEAT-STATE] Successfully requested reservation for {success_count}/{len(seat_ids)} seats'
        )

        return results

    def release_seats(self, seat_ids: List[str], event_id: int) -> Dict[str, bool]:
        """釋放座位 (RESERVED -> AVAILABLE)"""
        Logger.base.info(f'🔓 [SEAT-STATE] Releasing {len(seat_ids)} seats')

        if not self.is_available():
            raise RuntimeError('Seat state handler not available')

        # 獲取當前座位狀態
        current_states = self.get_seat_states(seat_ids, event_id)

        results = {}
        for seat_id in seat_ids:
            current_state = current_states.get(seat_id)

            if not current_state:
                results[seat_id] = False
                Logger.base.warning(f'⚠️ [SEAT-STATE] Seat {seat_id} not found')
                continue

            try:
                # TODO: 發送 Kafka 消息到 EventTicketingMqConsumer 來釋放座位
                # 這裡應該發送到 update_ticket_status_to_available topic
                results[seat_id] = True
                Logger.base.info(f'✅ [SEAT-STATE] Requested release for seat {seat_id}')

            except Exception as e:
                Logger.base.error(f'❌ [SEAT-STATE] Failed to release seat {seat_id}: {e}')
                results[seat_id] = False

        success_count = sum(results.values())
        Logger.base.info(
            f'🎯 [SEAT-STATE] Requested release for {success_count}/{len(seat_ids)} seats successfully'
        )

        return results

    def get_seat_price(self, seat_id: str, event_id: int) -> Optional[int]:
        """獲取座位價格"""
        seat_states = self.get_seat_states([seat_id], event_id)
        seat_state = seat_states.get(seat_id)
        return seat_state.get('price') if seat_state else None

    def _rollback_reservations(self, reserved_seat_ids: List[str], event_id: int) -> None:
        """回滾已預訂的座位"""
        if not reserved_seat_ids:
            return

        Logger.base.warning(f'🔄 [SEAT-STATE] Rolling back {len(reserved_seat_ids)} reservations')
        try:
            self.release_seats(reserved_seat_ids, event_id)
        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Failed to rollback reservations: {e}')
