"""
Release Seat Use Case
Seat release use case
"""

from src.platform.logging.loguru_io import Logger
from src.service.reservation.app.interface import ISeatStateCommandHandler
from src.service.reservation.app.dto import (
    ReleaseSeatRequest,
    ReleaseSeatResult,
    ReleaseSeatsBatchRequest,
    ReleaseSeatsBatchResult,
)


class ReleaseSeatUseCase:
    """Seat Release Use Case"""

    def __init__(self, seat_state_handler: ISeatStateCommandHandler) -> None:
        self.seat_state_handler = seat_state_handler

    @Logger.io
    async def execute(self, request: ReleaseSeatRequest) -> ReleaseSeatResult:
        """Execute single seat release"""
        try:
            Logger.base.info(f'🔓 [RELEASE-SEAT] Releasing seat {request.seat_position}')

            results = await self.seat_state_handler.release_seats(
                seat_positions=[request.seat_position],
                event_id=request.event_id,
                section=request.section,
                subsection=request.subsection,
            )

            success = results.get(request.seat_position, False)

            if success:
                Logger.base.info(f'✅ [RELEASE-SEAT] Seat {request.seat_position} released')
                return ReleaseSeatResult(success=True, seat_position=request.seat_position)
            else:
                error_msg = f'Failed to release seat {request.seat_position}'
                Logger.base.error(f'❌ [RELEASE-SEAT] {error_msg}')
                return ReleaseSeatResult(
                    success=False, seat_position=request.seat_position, error_message=error_msg
                )

        except Exception as e:
            error_msg = f'Error releasing seat {request.seat_position}: {str(e)}'
            Logger.base.error(f'❌ [RELEASE-SEAT] {error_msg}')
            return ReleaseSeatResult(
                success=False, seat_position=request.seat_position, error_message=error_msg
            )

    @Logger.io
    async def execute_batch(self, request: ReleaseSeatsBatchRequest) -> ReleaseSeatsBatchResult:
        """
        Execute batch seat release - Performance optimization

        Releases multiple seats in a SINGLE operation instead of N sequential calls.
        This reduces portal overhead and improves throughput significantly.
        """
        try:
            Logger.base.info(
                f'🔓 [RELEASE-SEATS-BATCH] Releasing {len(request.seat_positions)} seats in batch'
            )

            # Single call to release all seats
            results = await self.seat_state_handler.release_seats(
                seat_positions=request.seat_positions,
                event_id=request.event_id,
                section=request.section,
                subsection=request.subsection,
            )

            # Separate successful and failed seats
            successful_seats = [seat_pos for seat_pos, success in results.items() if success]
            failed_seats = [seat_pos for seat_pos, success in results.items() if not success]
            error_messages = {
                seat_pos: f'Failed to release seat {seat_pos}' for seat_pos in failed_seats
            }

            Logger.base.info(
                f'✅ [RELEASE-SEATS-BATCH] Released {len(successful_seats)}/{len(request.seat_positions)} seats'
            )

            if failed_seats:
                Logger.base.warning(
                    f'⚠️  [RELEASE-SEATS-BATCH] {len(failed_seats)} seats failed: {failed_seats}'
                )

            return ReleaseSeatsBatchResult(
                successful_seats=successful_seats,
                failed_seats=failed_seats,
                total_released=len(successful_seats),
                error_messages=error_messages,
            )

        except Exception as e:
            error_msg = f'Error releasing batch of seats: {str(e)}'
            Logger.base.error(f'❌ [RELEASE-SEATS-BATCH] {error_msg}')
            # All seats failed
            return ReleaseSeatsBatchResult(
                successful_seats=[],
                failed_seats=request.seat_positions,
                total_released=0,
                error_messages={seat_pos: error_msg for seat_pos in request.seat_positions},
            )
