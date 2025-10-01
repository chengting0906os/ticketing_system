"""
Seat State Handler Implementation
座位狀態處理器實現 - 使用 Bitfield + Counter 優化查詢
"""

import asyncio
from typing import Dict, List, Optional

from src.platform.logging.loguru_io import Logger
from src.seat_reservation.domain.seat_state_handler import SeatStateHandler
from src.seat_reservation.infra.seat_state_store import SeatStateStore


class SeatStateHandlerImpl(SeatStateHandler):
    """
    座位狀態處理器實現 - 使用 Kvrocks Bitfield + Counter

    職責:
    1. 查詢座位可用性 (從 Bitfield 讀取狀態, Counter 快速檢查)
    2. 預訂座位 (更新 Bitfield 狀態 + Counter)
    3. 釋放座位 (更新 Bitfield 狀態 + Counter)
    4. 確認付款 (更新 Bitfield 狀態)
    """

    def __init__(self, seat_state_store: SeatStateStore):
        self.repository = seat_state_store

    def is_available(self) -> bool:
        """檢查服務是否可用"""
        return True  # 簡化：總是可用

    def get_seat_states(self, seat_ids: List[str], event_id: int) -> Dict[str, Dict]:
        """獲取指定座位的狀態 - 從 Bitfield 讀取"""
        Logger.base.info(f'🔍 [SEAT-STATE] Getting states for {len(seat_ids)} seats')

        if not self.is_available():
            raise RuntimeError('Seat state handler not available')

        try:
            seat_states = {}

            for seat_id in seat_ids:
                # 解析座位 ID
                parts = seat_id.split('-')
                if len(parts) < 4:
                    Logger.base.warning(f'⚠️ [SEAT-STATE] Invalid seat_id: {seat_id}')
                    continue

                section, subsection, row, seat_num = (
                    parts[0],
                    int(parts[1]),
                    int(parts[2]),
                    int(parts[3]),
                )

                # 從 Bitfield 讀取狀態
                status = asyncio.run(
                    self.repository.get_seat_status(event_id, section, subsection, row, seat_num)
                )

                if status:
                    # 讀取價格 (從 metadata)
                    row_seats = asyncio.run(
                        self.repository.get_row_seats(event_id, section, subsection, row)
                    )
                    price = next((s['price'] for s in row_seats if s['seat_num'] == seat_num), 0)

                    seat_states[seat_id] = {
                        'seat_id': seat_id,
                        'event_id': event_id,
                        'status': status,
                        'price': price,
                    }

            Logger.base.info(
                f'✅ [SEAT-STATE] Retrieved {len(seat_states)} seat states from Bitfield'
            )
            return seat_states

        except Exception as e:
            Logger.base.error(f'❌ [SEAT-STATE] Failed to read seat states: {e}')
            return {}

    def get_available_seats_by_section(
        self, event_id: int, section: str, subsection: int, limit: Optional[int] = None
    ) -> List[Dict]:
        """按區域獲取可用座位 - 使用 Counter 優化查詢"""
        Logger.base.info(f'🔍 [SEAT-STATE] Getting available seats for {section}-{subsection}')

        if not self.is_available():
            raise RuntimeError('Seat state handler not available')

        available_seats = []

        try:
            # 優化策略：先查 Counter，再讀 Bitfield
            for row in range(1, 26):  # 25 排
                if limit and len(available_seats) >= limit:
                    break

                # 1. 查詢該排可售數 (O(1))
                row_count = asyncio.run(
                    self.repository.get_row_available_count(event_id, section, subsection, row)
                )

                if row_count == 0:
                    # 該排無可售座位，跳過
                    continue

                # 2. 讀取該排座位詳細狀態 (Bitfield 批量讀取)
                row_seats = asyncio.run(
                    self.repository.get_row_seats(event_id, section, subsection, row)
                )

                # 3. 篩選 AVAILABLE 座位
                for seat in row_seats:
                    if seat['status'] == 'AVAILABLE':
                        available_seats.append(
                            {
                                'seat_id': f'{section}-{subsection}-{row}-{seat["seat_num"]}',
                                'event_id': event_id,
                                'status': 'AVAILABLE',
                                'price': seat['price'],
                            }
                        )
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
