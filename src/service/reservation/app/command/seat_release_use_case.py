"""
Seat Release Use Case - PostgreSQL First Flow

New 5-Step Flow:
1. Validate Request
2. Idempotency Check (PostgreSQL)
3. PostgreSQL Write (booking + tickets)
4. Kvrocks Pipeline (update seat map)
5. SSE broadcast
"""

from opentelemetry import trace

from src.platform.exception.exceptions import DomainError
from src.platform.logging.loguru_io import Logger
from src.service.reservation.app.dto import (
    ReleaseSeatsBatchRequest,
    ReleaseSeatsBatchResult,
)
from src.service.reservation.app.interface import ISeatStateReleaseCommandHandler
from src.service.reservation.app.interface.i_booking_command_repo import (
    IBookingCommandRepo,
)
from src.service.shared_kernel.driven_adapter.pubsub_handler_impl import (
    PubSubHandlerImpl,
)


class SeatReleaseUseCase:
    """
    Release Seat Use Case - PostgreSQL First Flow

    New 5-Step Flow:
    1. Validate Request - Check seat_positions exists
    2. Idempotency Check - Query PostgreSQL booking table
    3. PostgreSQL Write - Update booking + tickets
    4. Kvrocks Pipeline - Update seat map (BITFIELD SET 0)
    5. SSE Broadcast - Notify users

    Design Principles:
    - PostgreSQL as source of truth for idempotency
    - Pipeline for batch seat map updates
    """

    def __init__(
        self,
        seat_state_handler: ISeatStateReleaseCommandHandler,
        booking_command_repo: IBookingCommandRepo,
        pubsub_handler: PubSubHandlerImpl,
    ) -> None:
        self.seat_state_handler = seat_state_handler
        self.booking_command_repo = booking_command_repo
        self.pubsub_handler = pubsub_handler
        self.tracer = trace.get_tracer(__name__)

    @Logger.io
    async def execute_batch(self, request: ReleaseSeatsBatchRequest) -> ReleaseSeatsBatchResult:
        """
        Execute seat release - PostgreSQL First Flow

        New 5-Step Flow:
        1. Validate Request
        2. Idempotency Check (PostgreSQL)
        3. PostgreSQL Write (booking + tickets)
        4. Kvrocks Pipeline (update seat map)
        5. SSE Broadcast
        """
        with self.tracer.start_as_current_span(
            'use_case.release_seats',
            attributes={
                'booking.id': request.booking_id,
                'event.id': request.event_id,
                'buyer.id': request.buyer_id,
                'seat.count': len(request.seat_positions),
            },
        ):
            try:
                Logger.base.info(
                    f'🔓 [RELEASE] Processing release for booking {request.booking_id}, '
                    f'buyer {request.buyer_id}, {len(request.seat_positions)} seats'
                )

                # ========== Step 1: Validate Request ==========
                self._validate_request(request)

                # ========== Step 2: Idempotency Check (PostgreSQL) ==========
                existing_booking = await self.booking_command_repo.get_by_id(
                    booking_id=request.booking_id
                )
                if existing_booking and existing_booking.status == 'CANCELLED':
                    Logger.base.info(
                        f'✅ [IDEMPOTENCY] Booking {request.booking_id} already CANCELLED, '
                        'completing remaining steps'
                    )
                    return await self._complete_success_flow(
                        request=request,
                        seat_positions=existing_booking.seat_positions,
                    )

                if not existing_booking or existing_booking.status != 'PENDING_PAYMENT':
                    error_msg = f'Booking {request.booking_id} not in PENDING_PAYMENT status'
                    Logger.base.warning(f'⚠️ [RELEASE] {error_msg}')
                    return self._error_result(request, error_msg)

                # ========== Step 3: PostgreSQL Write ==========
                await self.booking_command_repo.update_status_to_cancelled_and_release_tickets(
                    booking_id=request.booking_id
                )
                Logger.base.info(
                    f'✅ [RELEASE] PostgreSQL write complete for booking {request.booking_id}'
                )

                # ========== Step 4 + 5: Kvrocks + SSE ==========
                return await self._complete_success_flow(
                    request=request,
                    seat_positions=request.seat_positions,
                )

            except DomainError as e:
                Logger.base.warning(f'⚠️ [RELEASE] Domain error: {e}')
                return self._error_result(request, str(e))

            except Exception as e:
                Logger.base.exception(f'❌ [RELEASE] Unexpected error: {e}')
                return self._error_result(request, 'Internal server error')

    def _validate_request(self, request: ReleaseSeatsBatchRequest) -> None:
        if not request.seat_positions:
            raise DomainError('seat_positions is required')

    def _build_seats_to_release(
        self, *, seat_positions: list[str], cols: int
    ) -> list[tuple[str, int]]:
        """Build seats_to_release tuples for Kvrocks update."""
        return [
            (
                seat_id,
                (int(seat_id.split('-')[0]) - 1) * cols + (int(seat_id.split('-')[1]) - 1),
            )
            for seat_id in seat_positions
        ]

    async def _complete_success_flow(
        self,
        *,
        request: ReleaseSeatsBatchRequest,
        seat_positions: list[str],
    ) -> ReleaseSeatsBatchResult:
        """Complete Step 4 (Kvrocks) + Step 5 (SSE) + return success result."""
        # Fetch config for seat index calculation
        config_result = await self.seat_state_handler.fetch_release_config(
            event_id=request.event_id,
            section=request.section,
            subsection=request.subsection,
        )
        if not config_result['success']:
            return self._error_result(request, config_result['error_message'])

        cols = config_result['cols']
        seats_to_release = self._build_seats_to_release(seat_positions=seat_positions, cols=cols)

        # Step 4: Kvrocks Pipeline (idempotent - SET 0 when already 0 is no-op)
        await self.seat_state_handler.update_seat_map_release(
            event_id=request.event_id,
            section=request.section,
            subsection=request.subsection,
            booking_id=request.booking_id,
            seats_to_release=seats_to_release,
        )
        Logger.base.info(f'✅ [RELEASE] Kvrocks seat map updated for booking {request.booking_id}')

        # Step 5: SSE Broadcast
        await self.pubsub_handler.schedule_stats_broadcast(event_id=request.event_id)
        await self.pubsub_handler.publish_booking_update(
            user_id=request.buyer_id,
            event_id=request.event_id,
            event_data={
                'event_type': 'booking_updated',
                'event_id': request.event_id,
                'booking_id': request.booking_id,
                'status': 'CANCELLED',
                'tickets': [],
            },
        )

        return ReleaseSeatsBatchResult(
            successful_seats=seat_positions,
            failed_seats=[],
            total_released=len(seat_positions),
            error_messages={},
        )

    @staticmethod
    def _error_result(request: ReleaseSeatsBatchRequest, error_msg: str) -> ReleaseSeatsBatchResult:
        return ReleaseSeatsBatchResult(
            successful_seats=[],
            failed_seats=request.seat_positions,
            total_released=0,
            error_messages={seat_pos: error_msg for seat_pos in request.seat_positions},
        )
