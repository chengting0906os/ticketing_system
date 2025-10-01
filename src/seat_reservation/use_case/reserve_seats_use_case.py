"""
Reserve Seats Use Case
座位預訂用例 - 基於 Kvrocks 狀態管理的無鎖實現
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
from src.seat_reservation.domain.seat_state_handler import SeatStateHandler
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
    2. 直接操作 Kvrocks 狀態進行預訂
    3. 處理預訂結果並回傳

    注意：直接使用 Kvrocks 狀態，不通過 Kafka 命令！
    """

    def __init__(
        self, seat_selection_domain: SeatSelectionDomain, seat_state_handler: SeatStateHandler
    ):
        self.seat_domain = seat_selection_domain
        self.seat_state_handler = seat_state_handler

    @Logger.io
    async def reserve_seats(self, request: ReservationRequest) -> ReservationResult:
        """
        執行座位預訂

        流程：
        1. 驗證請求
        2. 獲取可用座位（從某處...待實現）
        3. 使用領域服務選擇座位
        4. 發送預訂命令到 Kvrocks（通過 Kafka）
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

            # 3. 獲取可用座位（TODO: 這裡需要從 Kvrocks 或 PostgreSQL 獲取）
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

            # 5. 直接預訂座位到 Kvrocks
            reservation_success = await self._reserve_seats_directly(
                booking_id=request.booking_id,
                buyer_id=request.buyer_id,
                selected_seats=selection_result.selected_seats,
                event_id=request.event_id,
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
                    error_message='Failed to reserve seats directly in Kvrocks',
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
        獲取可用座位 - 從 Kvrocks 狀態查詢
        """
        # 使用 SeatStateHandler 獲取可用座位
        if request.section_filter and request.subsection_filter:
            # 如果有特定區域篩選，直接查詢該區域
            seat_data_list = self.seat_state_handler.get_available_seats_by_section(
                event_id=event_id,
                section=request.section_filter,
                subsection=request.subsection_filter,
                limit=request.quantity * 2 if request.quantity else None,  # 獲取多一些以便選擇
            )
        else:
            # 沒有特定區域篩選，獲取所有區域
            all_seats = []
            for section in ['A', 'B']:
                for subsection in [1, 2]:
                    section_seats = self.seat_state_handler.get_available_seats_by_section(
                        event_id=event_id,
                        section=section,
                        subsection=subsection,
                        limit=50,  # 每個區域限制數量
                    )
                    all_seats.extend(section_seats)
            seat_data_list = all_seats

        # 轉換為 AvailableSeat 領域物件
        available_seats = []
        for seat_data in seat_data_list:
            if seat_data.get('status') != 'AVAILABLE':
                continue

            # 解析座位位置
            seat_id = seat_data['seat_id']
            try:
                parts = seat_id.split('-')
                if len(parts) >= 4:
                    section, subsection, row, seat = parts[:4]
                    seat_position = SeatPosition(
                        section=section, subsection=int(subsection), row=int(row), seat=int(seat)
                    )

                    available_seats.append(
                        AvailableSeat(
                            position=seat_position,
                            price=seat_data.get('price', 1000),
                            event_id=event_id,
                        )
                    )
            except (ValueError, IndexError) as e:
                Logger.base.warning(f'⚠️ [RESERVE] Invalid seat_id format: {seat_id}, error: {e}')
                continue

        # 應用過濾條件
        if request.section_filter:
            available_seats = [
                s for s in available_seats if s.position.section == request.section_filter
            ]

        if request.subsection_filter:
            available_seats = [
                s for s in available_seats if s.position.subsection == request.subsection_filter
            ]

        Logger.base.info(
            f'📊 [RESERVE] Found {len(available_seats)} available seats for event {event_id}'
        )

        return available_seats

    async def _reserve_seats_directly(
        self, booking_id: int, buyer_id: int, selected_seats: List[str], event_id: int
    ) -> bool:
        """
        直接預訂座位 - 使用 Kvrocks 狀態處理器
        """
        Logger.base.info(f'📤 [RESERVE] Directly reserving seats: {selected_seats}')

        try:
            # 使用 SeatStateHandler 直接預訂座位
            reservation_results = self.seat_state_handler.reserve_seats(
                seat_ids=selected_seats, booking_id=booking_id, buyer_id=buyer_id, event_id=event_id
            )

            # 檢查預訂結果
            successful_reservations = [
                seat_id for seat_id, success in reservation_results.items() if success
            ]
            failed_reservations = [
                seat_id for seat_id, success in reservation_results.items() if not success
            ]

            if failed_reservations:
                Logger.base.warning(f'⚠️ [RESERVE] Failed to reserve seats: {failed_reservations}')

                # 如果部分失敗，釋放已成功預訂的座位
                if successful_reservations:
                    Logger.base.info(
                        f'🔄 [RESERVE] Rolling back successful reservations: {successful_reservations}'
                    )
                    self.seat_state_handler.release_seats(successful_reservations, event_id)

                return False

            Logger.base.info(
                f'✅ [RESERVE] Successfully reserved {len(successful_reservations)} seats directly in Kvrocks'
            )
            return True

        except Exception as e:
            Logger.base.error(f'❌ [RESERVE] Failed to reserve seats directly: {e}')
            return False
