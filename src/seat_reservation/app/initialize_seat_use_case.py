"""
Initialize Seat Use Case
座位初始化用例
"""

from dataclasses import dataclass

from src.platform.logging.loguru_io import Logger
from src.seat_reservation.app.interface.i_seat_state_handler import SeatStateHandler


@dataclass
class InitializeSeatRequest:
    """座位初始化請求"""

    seat_id: str
    event_id: int
    price: int
    timestamp: str


@dataclass
class InitializeSeatResult:
    """座位初始化結果"""

    success: bool
    seat_id: str
    error_message: str = ''


class InitializeSeatUseCase:
    """座位初始化用例"""

    def __init__(self, seat_state_handler: SeatStateHandler):
        self.seat_state_handler = seat_state_handler

    async def execute(self, request: InitializeSeatRequest) -> InitializeSeatResult:
        """執行座位初始化"""
        try:
            Logger.base.info(f'🎫 [INIT-SEAT] Initializing seat {request.seat_id}')

            success = self.seat_state_handler.initialize_seat(
                seat_id=request.seat_id,
                event_id=request.event_id,
                price=request.price,
                timestamp=request.timestamp,
            )

            if success:
                Logger.base.info(f'✅ [INIT-SEAT] Seat {request.seat_id} initialized')
                return InitializeSeatResult(success=True, seat_id=request.seat_id)
            else:
                error_msg = f'Failed to initialize seat {request.seat_id}'
                Logger.base.error(f'❌ [INIT-SEAT] {error_msg}')
                return InitializeSeatResult(
                    success=False, seat_id=request.seat_id, error_message=error_msg
                )

        except Exception as e:
            error_msg = f'Error initializing seat {request.seat_id}: {str(e)}'
            Logger.base.error(f'❌ [INIT-SEAT] {error_msg}')
            return InitializeSeatResult(
                success=False, seat_id=request.seat_id, error_message=error_msg
            )
