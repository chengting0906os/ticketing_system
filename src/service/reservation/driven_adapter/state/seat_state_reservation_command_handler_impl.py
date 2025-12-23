"""
Seat State Reservation Command Handler Implementation

CQRS Command Side implementation for seat reservation.
"""

from typing import Dict, List

from opentelemetry import trace

from src.service.reservation.app.interface import ISeatStateReservationCommandHandler
from src.service.reservation.driven_adapter.state.reservation_helper.atomic_reservation_executor import (
    AtomicReservationExecutor,
)


class SeatStateReservationCommandHandlerImpl(ISeatStateReservationCommandHandler):
    """
    Seat State Reservation Command Handler Implementation (CQRS Command)

    Responsibility: Orchestrates seat reservation workflow.
    Delegates to AtomicReservationExecutor which handles the actual operations.
    """

    def __init__(self, *, reservation_executor: AtomicReservationExecutor) -> None:
        self.reservation_executor = reservation_executor
        self.tracer = trace.get_tracer(__name__)

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
        """Update seat map in Kvrocks via Pipeline (Step 5)."""
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
