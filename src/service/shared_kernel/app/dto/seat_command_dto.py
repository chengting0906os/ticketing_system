"""
Seat Command DTOs - Shared Kernel

座位命令 DTOs - 定義座位狀態變更操作的 domain contracts
包含：釋放座位、完成支付等命令操作的請求/結果
"""

from dataclasses import dataclass


# ========== Release Seat ==========


@dataclass
class ReleaseSeatRequest:
    """座位釋放請求"""

    seat_id: str
    event_id: int


@dataclass
class ReleaseSeatResult:
    """座位釋放結果"""

    success: bool
    seat_id: str
    error_message: str = ''

    @classmethod
    def success_result(cls, seat_id: str) -> 'ReleaseSeatResult':
        """創建成功結果"""
        return cls(success=True, seat_id=seat_id)

    @classmethod
    def failure_result(cls, seat_id: str, error: str) -> 'ReleaseSeatResult':
        """創建失敗結果"""
        return cls(success=False, seat_id=seat_id, error_message=error)


@dataclass
class ReleaseSeatsBatchRequest:
    """批次座位釋放請求 - Performance optimization for releasing multiple seats"""

    seat_ids: list[str]
    event_id: int


@dataclass
class ReleaseSeatsBatchResult:
    """批次座位釋放結果"""

    successful_seats: list[str]
    failed_seats: list[str]
    total_released: int
    error_messages: dict[str, str]  # seat_id -> error_message

    @classmethod
    def success_result(cls, seat_ids: list[str]) -> 'ReleaseSeatsBatchResult':
        """創建全部成功結果"""
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
        """創建部分成功結果"""
        return cls(
            successful_seats=successful_seats,
            failed_seats=failed_seats,
            total_released=len(successful_seats),
            error_messages=error_messages,
        )
