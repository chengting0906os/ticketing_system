"""
Seat State Command Handler Implementation

CQRS Command Side implementation for seat state management.
"""

from typing import Dict, List, Optional

from opentelemetry import trace

from src.platform.logging.loguru_io import Logger
from src.service.reservation.app.interface import ISeatStateCommandHandler
from src.service.reservation.driven_adapter.state.reservation_helper.atomic_release_executor import (
    AtomicReleaseExecutor,
)
from src.service.reservation.driven_adapter.state.reservation_helper.atomic_reservation_executor import (
    AtomicReservationExecutor,
)
from src.service.shared_kernel.domain.value_object import SelectionMode


class SeatStateCommandHandlerImpl(ISeatStateCommandHandler):
    """
    Seat State Command Handler Implementation (CQRS Command)

    Responsibility: Orchestrates seat reservation workflow.
    Delegates to AtomicReservationExecutor and AtomicReleaseExecutor
    which handle idempotency internally.
    """

    def __init__(
        self,
        *,
        reservation_executor: AtomicReservationExecutor,
        release_executor: AtomicReleaseExecutor,
    ) -> None:
        """
        Initialize Seat State Command Handler.

        Args:
            reservation_executor: Handles atomic seat reservation with idempotency.
            release_executor: Handles atomic seat release with idempotency.
        """
        self.reservation_executor = reservation_executor
        self.release_executor = release_executor
        self.tracer = trace.get_tracer(__name__)

    # ========== Helper Methods ==========

    @staticmethod
    def _error_result(message: str) -> Dict:
        """Create standardized error result"""
        return {
            'success': False,
            'reserved_seats': [],
            'total_price': 0,
            'subsection_stats': {},
            'event_stats': {},
            'error_message': message,
        }

    # ========== Public Interface ==========

    @Logger.io
    async def reserve_seats_atomic(
        self,
        *,
        event_id: int,
        booking_id: str,
        buyer_id: int,
        mode: str,
        section: str,
        subsection: int,
        quantity: int,
        seat_ids: Optional[List[str]] = None,
        # Config from upstream (avoids redundant Kvrocks lookups in Lua scripts)
        rows: Optional[int] = None,
        cols: Optional[int] = None,
        price: Optional[int] = None,
    ) -> Dict:
        with self.tracer.start_as_current_span(
            'seat_handler.reserve_atomic',
            attributes={
                'booking.id': booking_id,
            },
        ):
            if mode == SelectionMode.MANUAL:
                # Validate manual mode parameters
                if not seat_ids:
                    return self._error_result('Manual mode requires seat_ids')

                return await self._reserve_manual_seats(
                    event_id=event_id,
                    booking_id=booking_id,
                    buyer_id=buyer_id,
                    section=section,
                    subsection=subsection,
                    seat_ids=seat_ids,
                )
            elif mode == SelectionMode.BEST_AVAILABLE:
                return await self._reserve_best_available_seats(
                    event_id=event_id,
                    booking_id=booking_id,
                    section=section,
                    subsection=subsection,
                    quantity=quantity,
                    rows=rows,
                    cols=cols,
                    price=price,
                )
            else:
                return self._error_result(f'Invalid mode: {mode}')

    # ========== Reservation Workflows ==========

    async def _reserve_manual_seats(
        self,
        *,
        event_id: int,
        booking_id: str,
        buyer_id: int,
        section: str,
        subsection: int,
        seat_ids: List[str],
    ) -> Dict:
        """Reserve specified seats - Manual Mode (executor handles idempotency)"""
        with self.tracer.start_as_current_span(
            'seat_handler.reserve_manual',
            attributes={
                'booking.id': booking_id,
            },
        ):
            # Delegate to executor (idempotency handled internally)
            return await self.reservation_executor.execute_manual_reservation(
                event_id=event_id,
                section=section,
                subsection=subsection,
                booking_id=booking_id,
                seat_ids=seat_ids,
            )

    async def _reserve_best_available_seats(
        self,
        *,
        event_id: int,
        booking_id: str,
        section: str,
        subsection: int,
        quantity: int,
        # Config from upstream (avoids redundant Kvrocks lookups in Lua scripts)
        rows: Optional[int] = None,
        cols: Optional[int] = None,
        price: Optional[int] = None,
    ) -> Dict:
        """Automatically find and reserve consecutive seats - Best Available Mode"""
        with self.tracer.start_as_current_span(
            'seat_handler.reserve_best_available',
            attributes={
                'booking.id': booking_id,
            },
        ):
            # Validate config is present (should always be passed from upstream)
            if rows is None or cols is None or price is None:
                return self._error_result('Missing config: rows, cols, price required')

            # Delegate to executor (idempotency handled internally)
            return await self.reservation_executor.execute_find_and_reserve(
                event_id=event_id,
                section=section,
                subsection=subsection,
                booking_id=booking_id,
                quantity=quantity,
                rows=rows,
                cols=cols,
                price=price,
            )

    # ========== Split Methods for New 5-Step Flow ==========

    async def find_seats(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        quantity: int,
        rows: int,
        cols: int,
        price: int,
    ) -> Dict:
        """Find available seats via Lua script (BEST_AVAILABLE mode)."""
        with self.tracer.start_as_current_span(
            'seat_handler.find_seats',
            attributes={
                'event.id': event_id,
                'section': section,
                'subsection': subsection,
                'quantity': quantity,
            },
        ):
            return await self.reservation_executor.execute_find_seats(
                event_id=event_id,
                section=section,
                subsection=subsection,
                quantity=quantity,
                rows=rows,
                cols=cols,
                price=price,
            )

    async def verify_seats(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        seat_ids: List[str],
        price: int,
    ) -> Dict:
        """Verify specified seats are available via Lua script (MANUAL mode)."""
        with self.tracer.start_as_current_span(
            'seat_handler.verify_seats',
            attributes={
                'event.id': event_id,
                'section': section,
                'subsection': subsection,
                'seat_count': len(seat_ids),
            },
        ):
            return await self.reservation_executor.execute_verify_seats(
                event_id=event_id,
                section=section,
                subsection=subsection,
                seat_ids=seat_ids,
                price=price,
            )

    async def update_seat_map(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        booking_id: str,
        seats_to_reserve: List[tuple],
        total_price: int,
    ) -> Dict:
        """Update seat map in Kvrocks via Pipeline (Step 4 of new flow)."""
        with self.tracer.start_as_current_span(
            'seat_handler.update_seat_map',
            attributes={
                'booking.id': booking_id,
                'event.id': event_id,
                'seat_count': len(seats_to_reserve),
            },
        ):
            return await self.reservation_executor.execute_update_seat_map(
                event_id=event_id,
                section=section,
                subsection=subsection,
                booking_id=booking_id,
                seats_to_reserve=seats_to_reserve,
                total_price=total_price,
            )

    # ========== Release Methods ==========

    @Logger.io
    async def release_seats(
        self,
        *,
        booking_id: str,
        seat_positions: List[str],
        event_id: int,
        section: str,
        subsection: int,
    ) -> Dict[str, bool]:
        """
        Release seats (RESERVED -> AVAILABLE) with idempotency control.

        Delegates to AtomicReleaseExecutor which:
        1. Checks booking metadata for RELEASE_SUCCESS (idempotency)
        2. Releases seats atomically via pipeline
        3. Updates booking metadata to RELEASE_SUCCESS

        Args:
            booking_id: Booking ID (for idempotency)
            seat_positions: List of seat positions (format: "row-seat", e.g., "1-5")
            event_id: Event ID
            section: Section name (e.g., "A")
            subsection: Subsection number (e.g., 1)

        Returns:
            Dict mapping seat_position to success status
        """
        return await self.release_executor.execute_atomic_release(
            booking_id=booking_id,
            event_id=event_id,
            section=section,
            subsection=subsection,
            seat_positions=seat_positions,
        )
