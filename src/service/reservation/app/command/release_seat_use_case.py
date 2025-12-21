"""
Release Seat Use Case - Atomic operations for releasing seats

Symmetric with ReserveSeatsUseCase: Kvrocks + PostgreSQL + SSE
"""

from opentelemetry import trace

from src.platform.logging.loguru_io import Logger
from src.service.reservation.app.dto import (
    ReleaseSeatsBatchRequest,
    ReleaseSeatsBatchResult,
)
from src.service.reservation.app.interface import ISeatStateCommandHandler
from src.service.reservation.app.interface.i_booking_command_repo import (
    IBookingCommandRepo,
)
from src.service.shared_kernel.driven_adapter.pubsub_handler_impl import (
    PubSubHandlerImpl,
)


class ReleaseSeatUseCase:
    """
    Release Seat Use Case - Kvrocks + PostgreSQL

    Responsibility: Release seats in Kvrocks AND update PostgreSQL

    Flow:
    1. Release seats in Kvrocks (atomic operation)
    2. Update PostgreSQL (booking → CANCELLED, tickets → AVAILABLE)
    3. Schedule stats broadcast via SSE for real-time updates
    4. Publish booking update via SSE
    5. Return result

    Design Principles:
    - Unified writes: Kvrocks + PostgreSQL in one use case
    - Single Responsibility: Handles complete release flow
    - Symmetric with ReserveSeatsUseCase

    Dependencies:
    - seat_state_handler: For Kvrocks seat release
    - booking_command_repo: For PostgreSQL writes
    - pubsub_handler: For SSE + event_state broadcast via Kvrocks Pub/Sub
    """

    def __init__(
        self,
        seat_state_handler: ISeatStateCommandHandler,
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
        Execute batch seat release - Kvrocks + PostgreSQL

        Flow:
        1. Release seats in Kvrocks (atomic operation)
        2. Update PostgreSQL (booking → CANCELLED, tickets → AVAILABLE)
        3. Schedule stats broadcast for real-time updates
        4. Publish SSE for booking update
        5. Return result

        Design Rationale:
        - Unified writes: Kvrocks + PostgreSQL in one use case
        - No Kafka hop between Kvrocks and PostgreSQL operations
        - SSE broadcast: Real-time UI updates

        Args:
            request: Release request with booking_id, buyer_id, seat_positions, etc.

        Returns:
            Release result with successful/failed seats
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

                # Step 1: Release seats in Kvrocks (with idempotency via booking metadata)
                # Note: This is atomic - either all succeed or all fail
                results = await self.seat_state_handler.release_seats(
                    booking_id=request.booking_id,
                    seat_positions=request.seat_positions,
                    event_id=request.event_id,
                    section=request.section,
                    subsection=request.subsection,
                )

                # Atomic operation: all succeed or all fail
                all_success = all(results.values())
                successful_seats = request.seat_positions if all_success else []

                Logger.base.info(
                    f'✅ [RELEASE] Kvrocks released {len(successful_seats)}/{len(request.seat_positions)} seats'
                )

                # Step 2: Update PostgreSQL (booking → CANCELLED, tickets → AVAILABLE)
                try:
                    await self.booking_command_repo.update_status_to_cancelled_and_release_tickets(
                        booking_id=request.booking_id
                    )
                    Logger.base.info(
                        f'✅ [RELEASE] PostgreSQL updated for booking {request.booking_id}'
                    )
                except Exception as e:
                    Logger.base.error(
                        f'❌ [RELEASE] Failed to update DB for booking {request.booking_id}: {e}'
                    )
                    # Don't fail the entire operation - Kvrocks release succeeded

                # Step 3: Schedule throttled stats broadcast (1s delay)
                await self.pubsub_handler.schedule_stats_broadcast(event_id=request.event_id)

                # Step 4: Publish SSE for real-time UI updates
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

                # Atomic: either all succeed or all fail
                failed_seats = [] if all_success else request.seat_positions
                return ReleaseSeatsBatchResult(
                    successful_seats=successful_seats,
                    failed_seats=failed_seats,
                    total_released=len(successful_seats),
                    error_messages={}
                    if all_success
                    else {seat_pos: 'Atomic release failed' for seat_pos in failed_seats},
                )

            except Exception as e:
                error_msg = f'Error releasing batch of seats: {str(e)}'
                Logger.base.error(f'❌ [RELEASE] {error_msg}')

                # Record exception on span
                span = trace.get_current_span()
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, error_msg))
                span.set_attribute('error', True)
                span.set_attribute('error.type', 'unexpected_error')

                # All seats failed
                return ReleaseSeatsBatchResult(
                    successful_seats=[],
                    failed_seats=request.seat_positions,
                    total_released=0,
                    error_messages={seat_pos: error_msg for seat_pos in request.seat_positions},
                )
