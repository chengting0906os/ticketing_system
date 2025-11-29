"""
Reservation Request Event

Event published by Booking Service to Reservation Service
when booking metadata is saved and ready for seat reservation.
"""

from datetime import datetime, timezone
from typing import List, Optional

import attrs

from src.service.shared_kernel.domain.value_object import SubsectionConfig


@attrs.define
class ReservationRequestEvent:
    """
    Event sent from Booking Service to Reservation Service.

    This event indicates that booking metadata has been saved to Kvrocks
    and the reservation process can begin.
    """

    booking_id: str  # UUID7 string
    buyer_id: int
    event_id: int
    section: str
    subsection: int
    quantity: int
    seat_selection_mode: str  # 'manual' or 'best_available'
    seat_positions: List[str]  # For manual mode: ["1-1", "1-2"]
    occurred_at: datetime
    # Config for downstream services (avoids redundant Kvrocks lookups)
    config: Optional[SubsectionConfig] = None

    @property
    def aggregate_id(self) -> str:
        return self.booking_id

    @classmethod
    def create(
        cls,
        *,
        booking_id: str,
        buyer_id: int,
        event_id: int,
        section: str,
        subsection: int,
        quantity: int,
        seat_selection_mode: str,
        seat_positions: List[str],
        config: Optional[SubsectionConfig] = None,
    ) -> 'ReservationRequestEvent':
        return cls(
            booking_id=booking_id,
            buyer_id=buyer_id,
            event_id=event_id,
            section=section,
            subsection=subsection,
            quantity=quantity,
            seat_selection_mode=seat_selection_mode,
            seat_positions=seat_positions,
            occurred_at=datetime.now(timezone.utc),
            config=config,
        )
