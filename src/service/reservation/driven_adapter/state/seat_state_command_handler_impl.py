"""
Seat State Command Handler Implementation

CQRS Command Side implementation for seat state management.
"""

from typing import Dict, List, Optional

from opentelemetry import trace
from src.service.reservation.driven_adapter.reservation_helper.atomic_reservation_executor import (
    AtomicReservationExecutor,
)
from src.service.reservation.driven_adapter.reservation_helper.payment_finalizer import (
    PaymentFinalizer,
)
from src.service.reservation.driven_adapter.reservation_helper.release_executor import (
    ReleaseExecutor,
)

from src.platform.logging.loguru_io import Logger
from src.service.reservation.app.interface import ISeatStateCommandHandler


class SeatStateCommandHandlerImpl(ISeatStateCommandHandler):
    """
    Seat State Command Handler Implementation (CQRS Command)

    Responsibility: Orchestrates seat reservation workflow using Lua scripts.
    All config fetching happens in Lua for single source of truth.
    """

    def __init__(
        self,
        *,
        reservation_executor: AtomicReservationExecutor,
        release_executor: ReleaseExecutor,
        payment_finalizer: PaymentFinalizer,
    ) -> None:
        """
        Initialize Seat State Command Handler.

        Args:
            reservation_executor: Handles atomic seat reservation operations.
            release_executor: Handles seat release operations.
            payment_finalizer: Handles payment finalization operations.
        """
        self.reservation_executor = reservation_executor
        self.release_executor = release_executor
        self.payment_finalizer = payment_finalizer
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
            if mode == 'manual':
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
            elif mode == 'best_available':
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
        """Reserve specified seats - Manual Mode (Lua fetches config + validates)"""
        with self.tracer.start_as_current_span(
            'seat_handler.reserve_manual',
            attributes={
                'booking.id': booking_id,
            },
        ):
            # Execute verify + reserve (Lua fetches config, generates bf_key internally)
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

            # Execute find + reserve (config passed via ARGV to Lua script)
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

    # ========== Other Command Methods ==========

    @Logger.io
    async def release_seats(self, seat_ids: List[str], event_id: int) -> Dict[str, bool]:
        """Release seats (RESERVED -> AVAILABLE)"""
        return await self.release_executor.release_seats(seat_ids=seat_ids, event_id=event_id)

    @Logger.io
    async def finalize_payment(self, *, seat_id: str, event_id: int) -> bool:
        """Finalize payment (RESERVED -> SOLD)"""
        return await self.payment_finalizer.finalize_seat_payment(
            seat_id=seat_id,
            event_id=event_id,
        )
