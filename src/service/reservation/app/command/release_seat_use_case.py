"""
Release Seat Use Case
Seat release use case
"""

from src.platform.logging.loguru_io import Logger
from src.service.shared_kernel.app.interface import ISeatStateCommandHandler
from src.service.shared_kernel.app.dto import (
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

    @Logger.io
    async def execute_batch(self, request: ReleaseSeatsBatchRequest) -> ReleaseSeatsBatchResult:
        """
        Execute batch seat release - Performance optimization

        Releases multiple seats in a SINGLE operation instead of N sequential calls.
        This reduces portal overhead and improves throughput significantly.
        """
        try:
            Logger.base.info(
                f'🔓 [RELEASE-SEATS-BATCH] Releasing {len(request.seat_ids)} seats in batch'
            )

            # Single call to release all seats
            results = await self.seat_state_handler.release_seats(
                seat_ids=request.seat_ids, event_id=request.event_id
            )

            # Separate successful and failed seats
            successful_seats = [seat_id for seat_id, success in results.items() if success]
            failed_seats = [seat_id for seat_id, success in results.items() if not success]
            error_messages = {
                seat_id: f'Failed to release seat {seat_id}' for seat_id in failed_seats
            }

            Logger.base.info(
                f'✅ [RELEASE-SEATS-BATCH] Released {len(successful_seats)}/{len(request.seat_ids)} seats'
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
                failed_seats=request.seat_ids,
                total_released=0,
                error_messages={seat_id: error_msg for seat_id in request.seat_ids},
            )
