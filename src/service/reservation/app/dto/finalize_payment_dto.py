"""Finalize payment DTOs for seat payment use case."""

import attrs


@attrs.define
class FinalizeSeatPaymentRequest:
    """Seat payment finalization request"""

    seat_position: str  # format: "row-seat", e.g., "1-5"
    event_id: int
    section: str
    subsection: int


@attrs.define
class FinalizeSeatPaymentResult:
    """Seat payment finalization result"""

    success: bool
    seat_position: str  # format: "row-seat", e.g., "1-5"
    error_message: str = ''
