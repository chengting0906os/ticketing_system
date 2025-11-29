"""Reservation DTOs for seat reservation use case."""

from typing import List, Optional

import attrs

from src.service.shared_kernel.domain.value_object import SubsectionConfig


@attrs.define
class ReservationRequest:
    """Seat reservation request"""

    booking_id: str  # Changed to str for UUID7
    buyer_id: int
    event_id: int
    selection_mode: str  # 'manual' or 'best_available'
    section_filter: str  # Required, not Optional
    subsection_filter: int  # Required, not Optional
    quantity: int  # Required, not Optional
    seat_positions: Optional[List[str]] = None  # Manually selected seat IDs
    # Config from upstream (avoids redundant Kvrocks lookups in Lua scripts)
    config: Optional[SubsectionConfig] = None


@attrs.define
class ReservationResult:
    """Seat reservation result"""

    success: bool
    booking_id: str  # Changed to str for UUID7
    reserved_seats: Optional[List[str]] = None
    total_price: int = 0
    error_message: Optional[str] = None
    event_id: Optional[int] = None
