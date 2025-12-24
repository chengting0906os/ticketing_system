"""
Release Seat DTOs

Request/Result DTOs for seat release operations.
"""

import attrs


@attrs.define
class ReleaseSeatsBatchRequest:
    """Minimal release request - all details fetched from DB using booking_id"""

    booking_id: str  # UUID7 booking ID (for PostgreSQL lookup)
    event_id: int  # Event ID (for topic routing)


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
