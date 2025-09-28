"""
Reserve Seats Use Case
座位預訂用例 - 基於 RocksDB 狀態管理的無鎖實現
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from src.seat_reservation.domain.seat_selection_domain import (
    AvailableSeat,
    SeatPosition,
    SeatSelectionDomain,
    SeatSelectionRequest,
    SelectionMode,
)
from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger


@dataclass
class ReservationRequest:
    """座位預訂請求"""

    booking_id: int
    buyer_id: int
    event_id: int
    selection_mode: str  # 'manual' or 'best_available'
    quantity: Optional[int] = None
    seat_positions: Optional[List[str]] = None  # 手動選擇的座位ID列表
    section_filter: Optional[str] = None
    subsection_filter: Optional[int] = None


@dataclass
class ReservationResult:
    """座位預訂結果"""

    success: bool
    booking_id: int
    reserved_seats: Optional[List[str]] = None
    total_price: int = 0
    error_message: Optional[str] = None
    event_id: Optional[int] = None


@dataclass
class SeatReservationCommand:
    """座位預訂命令事件"""

    booking_id: int
    seat_id: str
    action: str
    buyer_id: int
    occurred_at: datetime

    @property
    def aggregate_id(self) -> int:
        """業務聚合根ID，用於分區和關聯"""
        return self.booking_id


@dataclass
class SeatReservationResult:
    """座位預訂結果事件"""

    booking_id: int
    success: bool
    reserved_seats: List[str]
    total_price: int
    error_message: str
    event_id: int
    occurred_at: datetime

    @property
    def aggregate_id(self) -> int:
        """業務聚合根ID，用於分區和關聯"""
        return self.booking_id


class ReserveSeatsUseCase:
    """
    座位預訂用例

    這個 Use Case 負責：
    1. 使用領域服務選擇座位
    2. 發送預訂命令到 RocksDB 狀態處理器
    3. 處理預訂結果並回傳

    注意：這裡不直接操作 PostgreSQL！
    """

    def __init__(self, seat_selection_domain: SeatSelectionDomain):
        self.seat_domain = seat_selection_domain

    @Logger.io
    async def reserve_seats(self, request: ReservationRequest) -> ReservationResult:
        """
        執行座位預訂

        流程：
        1. 驗證請求
        2. 獲取可用座位（從某處...待實現）
        3. 使用領域服務選擇座位
        4. 發送預訂命令到 RocksDB（通過 Kafka）
        5. 等待並處理結果

        Args:
            request: 預訂請求

        Returns:
            預訂結果
        """
        try:
            Logger.base.info(
                f'🎯 [RESERVE] Processing reservation for booking {request.booking_id}, '
                f'buyer {request.buyer_id}, event {request.event_id}'
            )

            # 1. 驗證請求
            self._validate_request(request)

            # 2. 轉換為領域請求
            selection_request = self._to_domain_request(request)

            # 3. 獲取可用座位（TODO: 這裡需要從 RocksDB 或 PostgreSQL 獲取）
            available_seats = await self._get_available_seats(request.event_id, request)

            if not available_seats:
                return ReservationResult(
                    success=False,
                    booking_id=request.booking_id,
                    error_message='No seats available for this event',
                    event_id=request.event_id,
                )

            # 4. 使用領域服務選擇座位
            selection_result = self.seat_domain.select_seats(selection_request, available_seats)

            if not selection_result.success:
                return ReservationResult(
                    success=False,
                    booking_id=request.booking_id,
                    error_message=selection_result.error_message or 'Selection failed',
                    event_id=request.event_id,
                )

            # 5. 發送預訂命令到 RocksDB（通過 Kafka）
            reservation_success = await self._send_reservation_commands(
                booking_id=request.booking_id,
                buyer_id=request.buyer_id,
                selected_seats=selection_result.selected_seats,
            )

            if reservation_success:
                Logger.base.info(
                    f'✅ [RESERVE] Successfully reserved {len(selection_result.selected_seats)} seats '
                    f'for booking {request.booking_id}'
                )

                return ReservationResult(
                    success=True,
                    booking_id=request.booking_id,
                    reserved_seats=selection_result.selected_seats,
                    total_price=selection_result.total_price or 0,
                    event_id=request.event_id,
                )
            else:
                return ReservationResult(
                    success=False,
                    booking_id=request.booking_id,
                    error_message='Failed to reserve seats in RocksDB',
                    event_id=request.event_id,
                )

        except DomainError as e:
            Logger.base.warning(f'⚠️ [RESERVE] Domain error: {e}')
            return ReservationResult(
                success=False,
                booking_id=request.booking_id,
                error_message=str(e),
                event_id=request.event_id,
            )
        except Exception as e:
            Logger.base.error(f'❌ [RESERVE] Unexpected error: {e}')
            return ReservationResult(
                success=False,
                booking_id=request.booking_id,
                error_message='Internal server error',
                event_id=request.event_id,
            )

    def _validate_request(self, request: ReservationRequest) -> None:
        """驗證預訂請求"""
        if request.selection_mode == 'manual':
            if not request.seat_positions:
                raise DomainError('Manual selection requires seat positions', 400)
            self.seat_domain.validate_selection_limits(len(request.seat_positions))

        elif request.selection_mode == 'best_available':
            if not request.quantity or request.quantity <= 0:
                raise DomainError('Best available selection requires valid quantity', 400)
            self.seat_domain.validate_selection_limits(request.quantity)

        else:
            raise DomainError(f'Invalid selection mode: {request.selection_mode}', 400)

    def _to_domain_request(self, request: ReservationRequest) -> SeatSelectionRequest:
        """轉換為領域請求"""
        mode = (
            SelectionMode.MANUAL
            if request.selection_mode == 'manual'
            else SelectionMode.BEST_AVAILABLE
        )

        return SeatSelectionRequest(
            mode=mode,
            event_id=request.event_id,
            buyer_id=request.buyer_id,
            quantity=request.quantity,
            manual_seats=request.seat_positions,
            section_filter=request.section_filter,
            subsection_filter=request.subsection_filter,
        )

    async def _get_available_seats(
        self, event_id: int, request: ReservationRequest
    ) -> List[AvailableSeat]:
        """
        獲取可用座位

        TODO: 這裡需要實現從 RocksDB 或 PostgreSQL 查詢可用座位的邏輯
        現在先返回模擬數據
        """
        # 模擬數據 - 實際實現需要查詢真實數據源
        mock_seats = []

        for section in ['A', 'B']:
            for subsection in [1, 2]:
                for row in range(1, 6):  # 5排
                    for seat in range(1, 21):  # 每排20個座位
                        seat_position = SeatPosition(
                            section=section, subsection=subsection, row=row, seat=seat
                        )

                        mock_seats.append(
                            AvailableSeat(
                                position=seat_position,
                                price=1000 + (row * 100),  # 前排價格高
                                event_id=event_id,
                            )
                        )

        # 應用過濾條件
        if request.section_filter:
            mock_seats = [s for s in mock_seats if s.position.section == request.section_filter]

        if request.subsection_filter:
            mock_seats = [
                s for s in mock_seats if s.position.subsection == request.subsection_filter
            ]

        Logger.base.info(
            f'📊 [RESERVE] Found {len(mock_seats)} available seats for event {event_id}'
        )

        return mock_seats

    async def _send_reservation_commands(
        self, booking_id: int, buyer_id: int, selected_seats: List[str]
    ) -> bool:
        """
        發送預訂命令到 RocksDB（通過 Kafka）
        """
        Logger.base.info(f'📤 [RESERVE] Sending reservation commands for seats: {selected_seats}')

        try:
            # 導入事件發布器
            from datetime import datetime

            from src.shared.message_queue.unified_mq_publisher import publish_domain_event

            # 為每個座位發送預訂命令
            for seat_id in selected_seats:
                command_event = SeatReservationCommand(
                    booking_id=booking_id,
                    seat_id=seat_id,
                    action='RESERVE',
                    buyer_id=buyer_id,
                    occurred_at=datetime.now(),
                )

                # 使用座位ID作為partition key確保同一座位的命令順序處理
                await publish_domain_event(
                    event=command_event, topic='seat-commands', partition_key=seat_id
                )

            Logger.base.info(
                f'✅ [RESERVE] Successfully sent {len(selected_seats)} reservation commands'
            )
            return True

        except Exception as e:
            Logger.base.error(f'❌ [RESERVE] Failed to send reservation commands: {e}')
            return False


# 依賴注入工廠
def create_reserve_seats_use_case() -> ReserveSeatsUseCase:
    """創建座位預訂用例實例"""
    seat_domain = SeatSelectionDomain()
    return ReserveSeatsUseCase(seat_domain)
