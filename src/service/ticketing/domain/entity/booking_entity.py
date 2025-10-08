from datetime import datetime
from enum import StrEnum
from typing import List, Optional

import attrs

from src.platform.exception.exceptions import DomainError
from src.platform.logging.loguru_io import Logger


class SeatSelectionMode(StrEnum):
    MANUAL = 'manual'
    BEST_AVAILABLE = 'best_available'


class BookingStatus(StrEnum):
    PROCESSING = 'processing'
    PENDING_PAYMENT = 'pending_payment'
    PAID = 'paid'
    CANCELLED = 'cancelled'
    COMPLETED = 'completed'
    FAILED = 'failed'


# Validation logic moved to shared validators module


@attrs.define
class Booking:
    buyer_id: int
    event_id: int
    total_price: int
    section: str
    subsection: int
    quantity: int
    seat_selection_mode: str
    seat_positions: Optional[List[str]] = attrs.field(factory=list)
    status: BookingStatus = BookingStatus.PROCESSING
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None

    @classmethod
    @Logger.io
    def create(
        cls,
        *,
        id: int = 0,
        buyer_id: int,
        event_id: int,
        total_price: int = 0,
        section: str,
        subsection: int,
        seat_selection_mode: str,
        seat_positions: List[str],
        quantity: int,
    ) -> 'Booking':
        # Validate seat selection parameters
        if seat_selection_mode == 'manual':
            if not seat_positions:
                raise DomainError('seat_positions is required for manual selection', 400)
            if quantity != len(seat_positions):
                raise DomainError(
                    'quantity must match the number of selected seat positions for manual selection',
                    400,
                )
            if len(seat_positions) > 4:
                raise DomainError('Maximum 4 tickets per booking', 400)
        elif seat_selection_mode == 'best_available':
            if seat_positions and len(seat_positions) > 0:
                raise DomainError('seat_positions must be empty for best_available selection', 400)
            if quantity < 1 or quantity > 4:
                raise DomainError('quantity must be between 1 and 4', 400)
        else:
            raise DomainError(
                'seat_selection_mode must be either "manual" or "best_available"', 400
            )

        # Validate seat_positions format for manual selection (now simple string format like "1-1", "1-2")

        if seat_selection_mode == 'manual' and seat_positions:
            for seat_position in seat_positions:
                try:
                    # Validate seat_position format: "row-seat" (e.g., "1-1", "2-3")
                    if not isinstance(seat_position, str):
                        raise DomainError('seat_position must be a string', 400)

                    parts = seat_position.split('-')
                    if len(parts) != 2:
                        raise DomainError(
                            'Invalid seat format. Expected: row-seat (e.g., 1-1, 2-3)', 400
                        )

                    try:
                        row = int(parts[0])
                        column = int(parts[1])
                        if row <= 0 or column <= 0:
                            raise DomainError('Row and seat numbers must be positive', 400)
                    except ValueError:
                        raise DomainError(
                            'Invalid seat format. Expected: row-seat (e.g., 1-1, 2-3)', 400
                        )

                except Exception as e:
                    if isinstance(e, DomainError):
                        raise
                    raise DomainError(f'Invalid seat_positions format: {e}', 400)

        # For manual mode, validate that tickets are selected
        if seat_selection_mode == 'manual' and not seat_positions:
            raise DomainError('No tickets selected for booking', 400)

        return cls(
            buyer_id=buyer_id,
            event_id=event_id,
            section=section,
            subsection=subsection,
            total_price=total_price,
            seat_selection_mode=seat_selection_mode,
            status=BookingStatus.PROCESSING,
            seat_positions=seat_positions,
            quantity=quantity,
            id=0 if id == 0 else id,
        )

    @Logger.io
    def mark_as_pending_payment_and_update_newest_info(
        self,
        *,
        total_price: int,
        seat_positions: list[str],
    ) -> 'Booking':
        """
        將 booking 標記為待付款狀態，同時更新總價和座位資訊

        Args:
            total_price: 計算後的總價
            seat_positions: 確認的座位列表

        Returns:
            更新後的 Booking
        """
        now = datetime.now()
        return attrs.evolve(
            self,
            status=BookingStatus.PENDING_PAYMENT,
            total_price=total_price,
            seat_positions=seat_positions,
            updated_at=now,
        )

    @Logger.io
    def mark_as_paid(self) -> 'Booking':
        now = datetime.now()
        return attrs.evolve(self, status=BookingStatus.PAID, paid_at=now, updated_at=now)

    @Logger.io
    def mark_as_failed(self) -> 'Booking':
        now = datetime.now()
        return attrs.evolve(self, status=BookingStatus.FAILED, updated_at=now)

    @Logger.io
    def mark_as_completed(self) -> 'Booking':
        now = datetime.now()
        return attrs.evolve(self, status=BookingStatus.COMPLETED, updated_at=now)

    @Logger.io
    def cancel(self) -> 'Booking':
        now = datetime.now()
        return attrs.evolve(self, status=BookingStatus.CANCELLED, updated_at=now)
