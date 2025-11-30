"""Finalize payment DTOs for seat payment use case."""

import attrs


@attrs.define
class FinalizeSeatPaymentRequest:
    """Seat payment finalization request"""

    seat_id: str
    event_id: int


@attrs.define
class FinalizeSeatPaymentResult:
    """Seat payment finalization result"""

    success: bool
    seat_id: str
    error_message: str = ''
