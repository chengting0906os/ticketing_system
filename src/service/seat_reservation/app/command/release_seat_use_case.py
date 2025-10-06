"""
Release Seat Use Case
座位釋放用例
"""

from dataclasses import dataclass

from src.platform.logging.loguru_io import Logger
from src.service.seat_reservation.app.interface.i_seat_state_handler import ISeatStateHandler


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


class ReleaseSeatUseCase:
    """座位釋放用例"""

    def __init__(self, seat_state_handler: ISeatStateHandler):
        self.seat_state_handler = seat_state_handler

    @Logger.io
    async def execute(self, request: ReleaseSeatRequest) -> ReleaseSeatResult:
        """執行座位釋放"""
        try:
            Logger.base.info(f'🔓 [RELEASE-SEAT] Releasing seat {request.seat_id}')

            results = await self.seat_state_handler.release_seats(
                seat_ids=[request.seat_id], event_id=request.event_id
            )

            success = results.get(request.seat_id, False)

            if success:
                Logger.base.info(f'✅ [RELEASE-SEAT] Seat {request.seat_id} released')
                return ReleaseSeatResult(success=True, seat_id=request.seat_id)
            else:
                error_msg = f'Failed to release seat {request.seat_id}'
                Logger.base.error(f'❌ [RELEASE-SEAT] {error_msg}')
                return ReleaseSeatResult(
                    success=False, seat_id=request.seat_id, error_message=error_msg
                )

        except Exception as e:
            error_msg = f'Error releasing seat {request.seat_id}: {str(e)}'
            Logger.base.error(f'❌ [RELEASE-SEAT] {error_msg}')
            return ReleaseSeatResult(
                success=False, seat_id=request.seat_id, error_message=error_msg
            )
