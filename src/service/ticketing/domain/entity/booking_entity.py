from datetime import datetime, timezone
from enum import StrEnum
from typing import List, Optional
from uuid_utils import UUID

import attrs

from src.platform.exception.exceptions import DomainError
from src.platform.logging.loguru_io import Logger


class SeatSelectionMode(StrEnum):
    MANUAL = 'manual'
    BEST_AVAILABLE = 'best_available'


class BookingStatus(StrEnum):
    PROCESSING = 'processing'
    PENDING_PAYMENT = 'pending_payment'
    CANCELLED = 'cancelled'
    COMPLETED = 'completed'
    FAILED = 'failed'


# Validation logic moved to shared validators module


@attrs.define
class Booking:
    id: UUID
    buyer_id: int
    event_id: int
    total_price: int
    section: str
    subsection: int
    quantity: int
    seat_selection_mode: str
    seat_positions: Optional[List[str]] = attrs.field(factory=list)
    status: BookingStatus = BookingStatus.PROCESSING
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None

    @classmethod
    @Logger.io
    def create(
        cls,
        *,
        id: UUID,
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

        now = datetime.now(timezone.utc)
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
            id=id,
            created_at=now,
            updated_at=now,
        )

    @Logger.io
    def mark_as_pending_payment_and_update_newest_info(
        self,
        *,
        total_price: int,
        seat_positions: list[str],
    ) -> 'Booking':
        """
        Mark booking as pending payment and update price and seat info

        Args:
            total_price: Calculated total price
            seat_positions: Confirmed seat positions

        Returns:
            Updated Booking
        """
        now = datetime.now(timezone.utc)
        return attrs.evolve(
            self,
            status=BookingStatus.PENDING_PAYMENT,
            total_price=total_price,
            seat_positions=seat_positions,
            updated_at=now,
        )

    @Logger.io
    def mark_as_failed(self) -> 'Booking':
        now = datetime.now(timezone.utc)
        return attrs.evolve(self, status=BookingStatus.FAILED, updated_at=now)

    @Logger.io
    def validate_can_be_paid(self) -> None:
        """
        Validate if booking can be paid (Domain layer validation logic)

        Raises:
            DomainError: When booking status does not allow payment
        """
        if self.status == BookingStatus.COMPLETED:
            raise DomainError('Booking already paid')
        elif self.status == BookingStatus.CANCELLED:
            raise DomainError('Cannot pay for cancelled booking')
        elif self.status != BookingStatus.PENDING_PAYMENT:
            raise DomainError('Booking is not in a payable state')

    @Logger.io
    def mark_as_completed(self) -> 'Booking':
        now = datetime.now(timezone.utc)
        return attrs.evolve(self, status=BookingStatus.COMPLETED, paid_at=now, updated_at=now)

    @Logger.io
    def cancel(self) -> 'Booking':
        """
        Cancel booking (Domain validation)

        Raises:
            DomainError: When booking status does not allow cancellation
        """
        # Domain rule: Only PROCESSING or PENDING_PAYMENT status can be cancelled
        if self.status == BookingStatus.COMPLETED:
            raise DomainError('Cannot cancel completed booking')
        elif self.status == BookingStatus.CANCELLED:
            raise DomainError('Booking already cancelled')
        elif self.status == BookingStatus.FAILED:
            raise DomainError('Cannot cancel failed booking')

        now = datetime.now(timezone.utc)
        return attrs.evolve(self, status=BookingStatus.CANCELLED, updated_at=now)
