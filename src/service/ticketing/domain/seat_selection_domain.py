"""
Seat Selection Domain
純粹的座位選擇領域邏輯 - 不碰任何基礎設施（PostgreSQL, Kafka 等）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID

from src.platform.exception.exceptions import DomainError
from src.platform.logging.loguru_io import Logger


class SelectionMode(Enum):
    """座位選擇模式"""

    MANUAL = 'manual'
    BEST_AVAILABLE = 'best_available'


@dataclass
class SeatPosition:
    """座位位置（值對象）"""

    section: str
    subsection: int
    row: int
    seat: int

    @property
    def seat_id(self) -> str:
        """座位標識符"""
        return f'{self.section}-{self.subsection}-{self.row}-{self.seat}'

    @classmethod
    def from_seat_id(cls, seat_id: str) -> 'SeatPosition':
        """從座位ID創建座位位置"""
        try:
            parts = seat_id.split('-')
            return cls(
                section=parts[0], subsection=int(parts[1]), row=int(parts[2]), seat=int(parts[3])
            )
        except (ValueError, IndexError):
            raise DomainError(
                f'Invalid seat ID format: {seat_id}. Expected: section-subsection-row-seat', 400
            )


@dataclass
class SeatSelectionRequest:
    """座位選擇請求（值對象）"""

    mode: SelectionMode
    event_id: UUID
    buyer_id: UUID
    quantity: Optional[int] = None
    manual_seats: Optional[List[str]] = None  # 手動選擇的座位ID列表
    section_filter: Optional[str] = None
    subsection_filter: Optional[int] = None

    def __post_init__(self):
        """請求驗證"""
        self._validate()

    def _validate(self) -> None:
        """驗證請求有效性"""
        if self.mode == SelectionMode.MANUAL:
            if not self.manual_seats:
                raise DomainError('Manual selection requires seat positions', 400)
            if len(self.manual_seats) > 4:
                raise DomainError('Maximum 4 seats per selection', 400)

        elif self.mode == SelectionMode.BEST_AVAILABLE:
            if not self.quantity or self.quantity <= 0:
                raise DomainError('Best available selection requires valid quantity', 400)
            if self.quantity > 4:
                raise DomainError('Maximum 4 seats per selection', 400)


@dataclass
class SeatSelectionResult:
    """座位選擇結果（值對象）"""

    success: bool
    selected_seats: List[str]  # 座位ID列表
    total_price: Optional[int] = None
    error_message: Optional[str] = None

    @classmethod
    def success_result(cls, seats: List[str], total_price: int = 0) -> 'SeatSelectionResult':
        """創建成功結果"""
        return cls(success=True, selected_seats=seats, total_price=total_price)

    @classmethod
    def failure_result(cls, error: str) -> 'SeatSelectionResult':
        """創建失敗結果"""
        return cls(success=False, selected_seats=[], error_message=error)


@dataclass
class AvailableSeat:
    """可用座位（實體）"""

    position: SeatPosition
    price: int
    event_id: UUID

    @property
    def seat_id(self) -> str:
        return self.position.seat_id


class SeatSelectionStrategy(ABC):
    """座位選擇策略（策略模式）"""

    @abstractmethod
    def select_seats(
        self, request: SeatSelectionRequest, available_seats: List[AvailableSeat]
    ) -> SeatSelectionResult:
        """選擇座位"""
        pass


class ManualSeatSelection(SeatSelectionStrategy):
    """手動座位選擇策略"""

    @Logger.io
    def select_seats(
        self, request: SeatSelectionRequest, available_seats: List[AvailableSeat]
    ) -> SeatSelectionResult:
        """
        驗證手動選擇的座位

        商業規則：
        1. 所有選擇的座位必須可用
        2. 所有座位必須屬於同一活動
        """
        if not request.manual_seats:
            return SeatSelectionResult.failure_result('No seats specified')

        # 建立可用座位映射
        available_map = {seat.seat_id: seat for seat in available_seats}

        # 驗證選擇的座位
        selected_seats = []
        total_price = 0
        unavailable_seats = []

        for seat_id in request.manual_seats:
            if seat_id in available_map:
                seat = available_map[seat_id]
                # 驗證座位屬於正確的活動
                if seat.event_id != request.event_id:
                    return SeatSelectionResult.failure_result(
                        f'Seat {seat_id} does not belong to event {request.event_id}'
                    )
                selected_seats.append(seat_id)
                total_price += seat.price
            else:
                unavailable_seats.append(seat_id)

        if unavailable_seats:
            return SeatSelectionResult.failure_result(
                f'Seats not available: {", ".join(unavailable_seats)}'
            )

        Logger.base.info(f'✅ Manual selection: {len(selected_seats)} seats, total: {total_price}')

        return SeatSelectionResult.success_result(selected_seats, total_price)


class BestAvailableSelection(SeatSelectionStrategy):
    """最佳可用座位選擇策略"""

    @Logger.io
    def select_seats(
        self, request: SeatSelectionRequest, available_seats: List[AvailableSeat]
    ) -> SeatSelectionResult:
        """
        選擇最佳可用座位

        商業規則：
        1. 優先選擇連續座位
        2. 優先選擇前排座位
        3. 相同排內優先選擇中間座位
        """
        if not request.quantity:
            return SeatSelectionResult.failure_result('Quantity required for best available')

        # 過濾活動座位
        event_seats = [seat for seat in available_seats if seat.event_id == request.event_id]

        if len(event_seats) < request.quantity:
            return SeatSelectionResult.failure_result(
                f'Not enough seats available. Need {request.quantity}, found {len(event_seats)}'
            )

        # 應用區域過濾
        if request.section_filter or request.subsection_filter:
            event_seats = self._apply_section_filter(event_seats, request)

        # 尋找最佳座位組合
        best_combination = self._find_best_combination(event_seats, request.quantity)

        if not best_combination:
            return SeatSelectionResult.failure_result(
                f'Cannot find {request.quantity} suitable seats'
            )

        selected_seats = [seat.seat_id for seat in best_combination]
        total_price = sum(seat.price for seat in best_combination)

        Logger.base.info(f'✅ Best available: {len(selected_seats)} seats, total: {total_price}')

        return SeatSelectionResult.success_result(selected_seats, total_price)

    def _apply_section_filter(
        self, seats: List[AvailableSeat], request: SeatSelectionRequest
    ) -> List[AvailableSeat]:
        """應用區域過濾"""
        filtered_seats = seats

        if request.section_filter:
            filtered_seats = [
                seat for seat in filtered_seats if seat.position.section == request.section_filter
            ]

        if request.subsection_filter:
            filtered_seats = [
                seat
                for seat in filtered_seats
                if seat.position.subsection == request.subsection_filter
            ]

        return filtered_seats

    def _find_best_combination(
        self, seats: List[AvailableSeat], quantity: int
    ) -> Optional[List[AvailableSeat]]:
        """
        尋找最佳座位組合

        策略：
        1. 按區域、子區域、排、座位號排序
        2. 優先尋找同排連續座位
        3. 如果沒有連續座位，選擇最前排的座位
        """
        # 按優先級排序
        sorted_seats = sorted(
            seats,
            key=lambda s: (
                s.position.section,
                s.position.subsection,
                s.position.row,
                s.position.seat,
            ),
        )

        # 嘗試尋找連續座位
        continuous_seats = self._find_continuous_seats(sorted_seats, quantity)
        if continuous_seats:
            return continuous_seats

        # 如果沒有連續座位，選擇最前排的座位
        return sorted_seats[:quantity]

    def _find_continuous_seats(
        self, seats: List[AvailableSeat], quantity: int
    ) -> Optional[List[AvailableSeat]]:
        """尋找連續座位"""
        # 按排分組
        rows: Dict[tuple, List[AvailableSeat]] = {}
        for seat in seats:
            row_key = (seat.position.section, seat.position.subsection, seat.position.row)
            if row_key not in rows:
                rows[row_key] = []
            rows[row_key].append(seat)

        # 在每排中尋找連續座位
        for row_key in sorted(rows.keys()):
            row_seats = sorted(rows[row_key], key=lambda s: s.position.seat)

            if len(row_seats) < quantity:
                continue

            # 檢查連續性
            for i in range(len(row_seats) - quantity + 1):
                if self._is_continuous_sequence(row_seats[i : i + quantity]):
                    return row_seats[i : i + quantity]

        return None

    def _is_continuous_sequence(self, seats: List[AvailableSeat]) -> bool:
        """檢查座位是否連續"""
        for i in range(1, len(seats)):
            if seats[i].position.seat != seats[i - 1].position.seat + 1:
                return False
        return True


class SeatSelectionDomain:
    """
    座位選擇領域服務

    這是領域層的核心服務，只包含純業務邏輯
    不依賴任何基礎設施（數據庫、消息隊列等）
    """

    def __init__(self):
        self.strategies = {
            SelectionMode.MANUAL: ManualSeatSelection(),
            SelectionMode.BEST_AVAILABLE: BestAvailableSelection(),
        }

    @Logger.io
    def select_seats(
        self, request: SeatSelectionRequest, available_seats: List[AvailableSeat]
    ) -> SeatSelectionResult:
        """
        執行座位選擇

        Args:
            request: 座位選擇請求
            available_seats: 可用座位列表（由外部提供）

        Returns:
            座位選擇結果
        """
        Logger.base.info(
            f'🎯 [SEAT_DOMAIN] Processing {request.mode.value} selection '
            f'for event {request.event_id}, buyer {request.buyer_id}'
        )

        # 選擇策略
        strategy = self.strategies[request.mode]

        # 執行選擇
        result = strategy.select_seats(request, available_seats)

        if result.success:
            Logger.base.info(
                f'✅ [SEAT_DOMAIN] Selected {len(result.selected_seats)} seats, '
                f'total price: {result.total_price}'
            )
        else:
            Logger.base.warning(f'❌ [SEAT_DOMAIN] Selection failed: {result.error_message}')

        return result

    def validate_selection_limits(self, seat_count: int) -> None:
        """
        驗證選擇限制

        商業規則：每次最多選擇 4 個座位
        """
        if seat_count <= 0:
            raise DomainError('Seat count must be positive', 400)
        if seat_count > 4:
            raise DomainError('Maximum 4 seats per selection', 400)
