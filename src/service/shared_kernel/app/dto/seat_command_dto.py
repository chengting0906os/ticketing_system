"""
Seat Command DTOs - Shared Kernel

Seat Command DTOs - Defines domain contracts for seat state change operations
Includes: Request/Result for seat release, payment completion, and other command operations
"""

from dataclasses import dataclass


# ========== Release Seat ==========


@dataclass
class ReleaseSeatRequest:
    """Seat release request"""

    seat_id: str
    event_id: int


@dataclass
class ReleaseSeatResult:
    """Seat release result"""

    success: bool
    seat_id: str
    error_message: str = ''

    @classmethod
    def success_result(cls, seat_id: str) -> 'ReleaseSeatResult':
        """Create success result"""
        return cls(success=True, seat_id=seat_id)

    @classmethod
    def failure_result(cls, seat_id: str, error: str) -> 'ReleaseSeatResult':
        """Create failure result"""
        return cls(success=False, seat_id=seat_id, error_message=error)


@dataclass
class ReleaseSeatsBatchRequest:
    """Batch seat release request - Performance optimization for releasing multiple seats"""

    seat_ids: list[str]
    event_id: int


@dataclass
class ReleaseSeatsBatchResult:
    """Batch seat release result"""

    successful_seats: list[str]
    failed_seats: list[str]
    total_released: int
    error_messages: dict[str, str]  # seat_id -> error_message

    @classmethod
    def success_result(cls, seat_ids: list[str]) -> 'ReleaseSeatsBatchResult':
        """Create all-success result"""
        return cls(
            successful_seats=seat_ids,
            failed_seats=[],
            total_released=len(seat_ids),
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
