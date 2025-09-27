"""
Seat Selection Domain Service
座位選擇的核心業務邏輯 - 獨立於基礎設施
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from abc import ABC, abstractmethod

from src.shared.logging.loguru_io import Logger
from src.shared.exception.exceptions import DomainError


@dataclass
class SeatSelectionRequest:
    """座位選擇請求"""

    event_id: int
    mode: str  # 'manual' or 'best_available'
    quantity: Optional[int] = None
    seat_positions: Optional[List[str]] = None
    section: Optional[str] = None
    subsection: Optional[int] = None


@dataclass
class SeatSelectionResult:
    """座位選擇結果"""

    success: bool
    selected_seats: List[str]
    ticket_ids: Optional[List[int]] = None
    error_message: Optional[str] = None


class SeatSelectionStrategy(ABC):
    """座位選擇策略接口"""

    @abstractmethod
    async def select_seats(
        self, request: SeatSelectionRequest, available_seats: List[Any]
    ) -> SeatSelectionResult:
        pass


class ManualSeatSelectionStrategy(SeatSelectionStrategy):
    """手動選擇座位策略"""

    @Logger.io
    async def select_seats(
        self, request: SeatSelectionRequest, available_seats: List[Any]
    ) -> SeatSelectionResult:
        """
        驗證手動選擇的座位是否可用
        """
        if not request.seat_positions:
            return SeatSelectionResult(
                success=False,
                selected_seats=[],
                error_message='No seats specified for manual selection',
            )

        # 將可用座位轉換為 set 以加快查找
        available_seat_ids = {
            f'{seat.section}-{seat.subsection}-{seat.row}-{seat.seat}' for seat in available_seats
        }

        # 檢查所有請求的座位是否可用
        unavailable_seats = []
        for seat_id in request.seat_positions:
            if seat_id not in available_seat_ids:
                unavailable_seats.append(seat_id)

        if unavailable_seats:
            return SeatSelectionResult(
                success=False,
                selected_seats=[],
                error_message=f'Seats not available: {", ".join(unavailable_seats)}',
            )

        return SeatSelectionResult(success=True, selected_seats=request.seat_positions)


class BestAvailableSelectionStrategy(SeatSelectionStrategy):
    """最佳可用座位選擇策略"""

    @Logger.io
    async def select_seats(
        self, request: SeatSelectionRequest, available_seats: List[Any]
    ) -> SeatSelectionResult:
        """
        自動選擇最佳的連續座位

        優先順序：
        1. 同一排的連續座位
        2. 較前排的座位
        3. 靠中間的座位
        """
        if not request.quantity or request.quantity <= 0:
            return SeatSelectionResult(
                success=False,
                selected_seats=[],
                error_message='Invalid quantity for best available selection',
            )

        # 按區域、排、座位號排序
        sorted_seats = sorted(
            available_seats, key=lambda s: (s.section, s.subsection, s.row, s.seat)
        )

        # 尋找連續座位
        continuous_seats = self._find_continuous_seats(sorted_seats, request.quantity)

        if continuous_seats:
            seat_ids = [f'{s.section}-{s.subsection}-{s.row}-{s.seat}' for s in continuous_seats]
            return SeatSelectionResult(success=True, selected_seats=seat_ids)

        return SeatSelectionResult(
            success=False,
            selected_seats=[],
            error_message=f'Cannot find {request.quantity} continuous seats',
        )

    def _find_continuous_seats(self, seats: List[Any], quantity: int) -> List[Any]:
        """
        在同一排中尋找連續座位
        """
        # 按排分組
        rows_map: Dict[tuple, List] = {}
        for seat in seats:
            row_key = (seat.section, seat.subsection, seat.row)
            if row_key not in rows_map:
                rows_map[row_key] = []
            rows_map[row_key].append(seat)

        # 在每一排中尋找連續座位
        for row_key in sorted(rows_map.keys()):
            row_seats = sorted(rows_map[row_key], key=lambda s: s.seat)

            if len(row_seats) < quantity:
                continue

            # 尋找連續的座位號
            for i in range(len(row_seats) - quantity + 1):
                continuous = True
                for j in range(1, quantity):
                    if row_seats[i + j].seat != row_seats[i].seat + j:
                        continuous = False
                        break

                if continuous:
                    return row_seats[i : i + quantity]

        return []


class SeatSelectionService:
    """
    座位選擇領域服務

    這是純業務邏輯，不依賴任何基礎設施
    """

    def __init__(self):
        self.strategies = {
            'manual': ManualSeatSelectionStrategy(),
            'best_available': BestAvailableSelectionStrategy(),
        }

    @Logger.io
    async def select_seats(
        self, request: SeatSelectionRequest, available_seats: List[Any]
    ) -> SeatSelectionResult:
        """
        根據請求選擇座位

        Args:
            request: 座位選擇請求
            available_seats: 可用座位列表

        Returns:
            座位選擇結果
        """
        # 驗證請求
        if request.mode not in self.strategies:
            return SeatSelectionResult(
                success=False,
                selected_seats=[],
                error_message=f'Invalid selection mode: {request.mode}',
            )

        # 根據模式選擇策略
        strategy = self.strategies[request.mode]

        # 執行選擇
        return await strategy.select_seats(request, available_seats)

    @Logger.io
    def validate_seat_count(self, count: int) -> None:
        """
        驗證座位數量

        業務規則：
        - 至少 1 個座位
        - 最多 4 個座位
        """
        if count <= 0:
            raise DomainError('Ticket count must be positive', 400)
        if count > 4:
            raise DomainError('Maximum 4 tickets per booking', 400)
