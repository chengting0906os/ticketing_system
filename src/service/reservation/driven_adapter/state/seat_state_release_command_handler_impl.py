"""
Seat State Release Command Handler Implementation

CQRS Command Side implementation for seat release.
"""

from typing import Dict, List

from opentelemetry import trace

from src.service.reservation.app.interface import ISeatStateReleaseCommandHandler
from src.service.reservation.driven_adapter.state.reservation_helper.atomic_release_executor import (
    AtomicReleaseExecutor,
)


class SeatStateReleaseCommandHandlerImpl(ISeatStateReleaseCommandHandler):
    """
    Seat State Release Command Handler Implementation (CQRS Command)

    Responsibility: Orchestrates seat release workflow.
    Delegates to AtomicReleaseExecutor which handles the actual operations.
    """

    def __init__(self, *, release_executor: AtomicReleaseExecutor) -> None:
        self.release_executor = release_executor
        self.tracer = trace.get_tracer(__name__)

    async def update_seat_map_release(
        self,
        *,
        event_id: int,
        section: str,
        subsection: int,
        booking_id: str,
        seats_to_release: List[tuple],
    ) -> Dict:
        """Update seat map in Kvrocks for release via Pipeline."""
        with self.tracer.start_as_current_span(
            'seat_handler.update_seat_map_release',
            attributes={
                'booking.id': booking_id,
                'event.id': event_id,
                'seat_count': len(seats_to_release),
            },
        ):
            return await self.release_executor.execute_update_seat_map_release(
                event_id=event_id,
                section=section,
                subsection=subsection,
                booking_id=booking_id,
                seats_to_release=seats_to_release,
            )
