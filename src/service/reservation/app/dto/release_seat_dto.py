"""
Release Seat DTOs

Request/Result DTOs for seat release operations.
"""

import attrs


# ========== Release Seat ==========


@attrs.define
class ReleaseSeatRequest:
    """Seat release request"""

    seat_position: str  # format: "row-seat", e.g., "1-5"
    event_id: int
    section: str
    subsection: int


@attrs.define
class ReleaseSeatResult:
    """Seat release result"""

    success: bool
    seat_position: str  # format: "row-seat", e.g., "1-5"
    error_message: str = ''

    @classmethod
    def success_result(cls, seat_position: str) -> 'ReleaseSeatResult':
        """Create success result"""
        return cls(success=True, seat_position=seat_position)

    @classmethod
    def failure_result(cls, seat_position: str, error: str) -> 'ReleaseSeatResult':
        """Create failure result"""
        return cls(success=False, seat_position=seat_position, error_message=error)


@attrs.define
class ReleaseSeatsBatchRequest:
    """Batch seat release request - Performance optimization for releasing multiple seats"""

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
