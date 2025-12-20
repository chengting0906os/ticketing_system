"""
Finalize Seat Payment Use Case
Seat payment completion use case
"""

from src.service.reservation.app.dto import (
    FinalizeSeatPaymentRequest,
    FinalizeSeatPaymentResult,
)

from src.platform.logging.loguru_io import Logger
from src.service.reservation.app.interface import ISeatStateCommandHandler


class FinalizeSeatPaymentUseCase:
    def __init__(self, seat_state_handler: ISeatStateCommandHandler) -> None:
        self.seat_state_handler = seat_state_handler

    @Logger.io
    async def execute(self, request: FinalizeSeatPaymentRequest) -> FinalizeSeatPaymentResult:
        try:
            Logger.base.info(
                f'💰 [FINALIZE-SEAT] Finalizing payment for seat {request.seat_position}'
            )

            success = await self.seat_state_handler.finalize_payment(
                seat_position=request.seat_position,
                event_id=request.event_id,
                section=request.section,
                subsection=request.subsection,
            )

            if success:
                Logger.base.info(f'✅ [FINALIZE-SEAT] Seat {request.seat_position} finalized')
                return FinalizeSeatPaymentResult(success=True, seat_position=request.seat_position)
            else:
                error_msg = f'Failed to finalize seat {request.seat_position}'
                Logger.base.error(f'❌ [FINALIZE-SEAT] {error_msg}')
                return FinalizeSeatPaymentResult(
                    success=False, seat_position=request.seat_position, error_message=error_msg
                )

        except Exception as e:
            error_msg = f'Error finalizing seat {request.seat_position}: {str(e)}'
            Logger.base.error(f'❌ [FINALIZE-SEAT] {error_msg}')
            return FinalizeSeatPaymentResult(
                success=False, seat_position=request.seat_position, error_message=error_msg
            )
