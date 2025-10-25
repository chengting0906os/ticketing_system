"""
Finalize Seat Payment Use Case
座位支付完成用例
"""

from dataclasses import dataclass
from uuid import UUID

from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.interface import ISeatStateCommandHandler


@dataclass
class FinalizeSeatPaymentRequest:
    """座位支付完成請求"""

    seat_id: str
    event_id: UUID
    timestamp: str


@dataclass
class FinalizeSeatPaymentResult:
    """座位支付完成結果"""

    success: bool
    seat_id: str
    error_message: str = ''


class FinalizeSeatPaymentUseCase:
    """座位支付完成用例"""

    def __init__(self, seat_state_handler: ISeatStateCommandHandler):
        self.seat_state_handler = seat_state_handler

    @Logger.io
    async def execute(self, request: FinalizeSeatPaymentRequest) -> FinalizeSeatPaymentResult:
        """執行座位支付完成"""
        try:
            Logger.base.info(f'💰 [FINALIZE-SEAT] Finalizing payment for seat {request.seat_id}')

            success = await self.seat_state_handler.finalize_payment(
                seat_id=request.seat_id,
                event_id=request.event_id,
                timestamp=request.timestamp,
            )

            if success:
                Logger.base.info(f'✅ [FINALIZE-SEAT] Seat {request.seat_id} finalized')
                return FinalizeSeatPaymentResult(success=True, seat_id=request.seat_id)
            else:
                error_msg = f'Failed to finalize seat {request.seat_id}'
                Logger.base.error(f'❌ [FINALIZE-SEAT] {error_msg}')
                return FinalizeSeatPaymentResult(
                    success=False, seat_id=request.seat_id, error_message=error_msg
                )

        except Exception as e:
            error_msg = f'Error finalizing seat {request.seat_id}: {str(e)}'
            Logger.base.error(f'❌ [FINALIZE-SEAT] {error_msg}')
            return FinalizeSeatPaymentResult(
                success=False, seat_id=request.seat_id, error_message=error_msg
            )
