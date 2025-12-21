"""
Release Seat DTOs

Request/Result DTOs for seat release operations.
"""

import attrs


@attrs.define
class ReleaseSeatsBatchRequest:
    """Batch seat release request - Performance optimization for releasing multiple seats"""

    booking_id: str  # UUID7 booking ID (for PostgreSQL update and tracing)
    buyer_id: int  # Buyer ID (for SSE broadcast)
    seat_positions: list[str]  # format: ["row-seat", ...], e.g., ["1-5", "1-6"]
    event_id: int
    section: str
    subsection: int


@attrs.define
class ReleaseSeatsBatchResult:
    """Batch seat release result"""

    successful_seats: list[str]
    failed_seats: list[str]
    total_released: int
    error_messages: dict[str, str]  # seat_position -> error_message

    @classmethod
    def success_result(cls, seat_positions: list[str]) -> 'ReleaseSeatsBatchResult':
        """Create all-success result"""
        return cls(
            successful_seats=seat_positions,
            failed_seats=[],
            total_released=len(seat_positions),
            error_messages={},
        )

    @classmethod
    def partial_result(
        cls, successful_seats: list[str], failed_seats: list[str], error_messages: dict[str, str]
    ) -> 'ReleaseSeatsBatchResult':
        """Create partial success result"""
        return cls(
            successful_seats=successful_seats,
            failed_seats=failed_seats,
            total_released=len(successful_seats),
            error_messages=error_messages,
        )
