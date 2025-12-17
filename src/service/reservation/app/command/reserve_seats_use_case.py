"""
Reserve Seats Use Case - Atomic operations based on Lua scripts + PostgreSQL writes
"""

from opentelemetry import trace
from uuid_utils import UUID

from src.platform.event.i_in_memory_broadcaster import IInMemoryEventBroadcaster
from src.platform.exception.exceptions import DomainError
from src.platform.logging.loguru_io import Logger
from src.service.reservation.app.dto import ReservationRequest, ReservationResult
from src.service.reservation.app.interface.i_booking_command_repo import (
    IBookingCommandRepo,
)
from src.service.reservation.app.interface.i_event_state_broadcaster import (
    IEventStateBroadcaster,
)
from src.service.reservation.app.interface import ISeatStateCommandHandler


class ReserveSeatsUseCase:
    """
    Reserve Seats Use Case - Kvrocks + PostgreSQL

    Responsibility: Manage seat state AND write to PostgreSQL

    Flow:
    1. Reserve seats in Kvrocks (atomic operation, returns prices)
    2. Write to PostgreSQL directly (booking + tickets)
    3. Broadcast via SSE for real-time updates
    4. Return result

    Design Principles:
    - Unified writes: Kvrocks + PostgreSQL in one service
    - Single Responsibility: Handles complete reservation flow
    - Minimal latency: No Kafka hop for PostgreSQL writes

    Dependencies:
    - seat_state_handler: For Kvrocks seat reservation
    - booking_command_repo: For PostgreSQL writes
    - event_state_broadcaster: For Redis Pub/Sub cache updates
    - sse_broadcaster: For SSE real-time notifications
    """

    def __init__(
        self,
        seat_state_handler: ISeatStateCommandHandler,
        booking_command_repo: IBookingCommandRepo,
        event_state_broadcaster: IEventStateBroadcaster,
        sse_broadcaster: IInMemoryEventBroadcaster,
    ) -> None:
        self.seat_state_handler = seat_state_handler
        self.booking_command_repo = booking_command_repo
        self.event_state_broadcaster = event_state_broadcaster
        self.sse_broadcaster = sse_broadcaster
        self.tracer = trace.get_tracer(__name__)

    @Logger.io
    async def reserve_seats(self, request: ReservationRequest) -> ReservationResult:
        """
        Execute seat reservation - Kvrocks + PostgreSQL

        Flow:
        1. Validate request
        2. Reserve seats in Kvrocks (atomic operation, returns prices)
        3. Write to PostgreSQL directly (booking + tickets)
        4. Broadcast via SSE for real-time updates
        5. Return result

        Design Rationale:
        - Unified writes: Kvrocks + PostgreSQL in one service
        - No Kafka hop: Faster end-to-end latency
        - SSE broadcast: Real-time UI updates

        Args:
            request: Reservation request

        Returns:
            Reservation result with booking and ticket info
        """
        with self.tracer.start_as_current_span(
            'use_case.reserve_seats',
            attributes={
                'booking.id': request.booking_id,
                'event.id': request.event_id,
                'buyer.id': request.buyer_id,
                'seat.mode': request.selection_mode,
                'seat.quantity': request.quantity or 0,
            },
        ):
            try:
                Logger.base.info(
                    f'🎯 [RESERVE] Processing reservation for booking {request.booking_id}, '
                    f'buyer {request.buyer_id}, event {request.event_id}'
                )

                # Step 1: Validate request
                self._validate_request(request)

                # Step 2: Reserve seats in Kvrocks (Pipeline, returns prices)
                # Pass config from upstream to avoid redundant Kvrocks lookups in Lua scripts
                result = await self.seat_state_handler.reserve_seats_atomic(
                    event_id=request.event_id,
                    booking_id=request.booking_id,
                    buyer_id=request.buyer_id,
                    mode=request.selection_mode,
                    section=request.section_filter,
                    subsection=request.subsection_filter,
                    quantity=request.quantity,
                    seat_ids=request.seat_positions if request.selection_mode == 'manual' else None,
                    rows=request.config.rows if request.config else None,
                    cols=request.config.cols if request.config else None,
                    price=request.config.price if request.config else None,
                )

                # Step 3: Handle result
                if result['success']:
                    reserved_seats = result['reserved_seats']
                    total_price = result['total_price']
                    subsection_stats = result.get('subsection_stats', {})
                    event_stats = result.get('event_stats', {})
                    event_state = result.get('event_state', {})

                    # Step 4a: Broadcast event_state update via Redis Pub/Sub (real-time cache)
                    await self.event_state_broadcaster.broadcast_event_state(
                        event_id=request.event_id, event_state=event_state
                    )
                    Logger.base.debug(
                        f'📤 [RESERVE] Broadcasted event_state to Redis Pub/Sub for event {request.event_id}'
                    )

                    # Step 4b: Write to PostgreSQL directly (booking + tickets)
                    pg_result = await self.booking_command_repo.create_booking_and_update_tickets_to_reserved(
                        booking_id=request.booking_id,
                        buyer_id=request.buyer_id,
                        event_id=request.event_id,
                        section=request.section_filter or '',
                        subsection=request.subsection_filter or 0,
                        seat_selection_mode=request.selection_mode,
                        reserved_seats=reserved_seats,
                        total_price=total_price,
                    )

                    Logger.base.info(
                        f'✅ [RESERVE] Kvrocks + PostgreSQL write complete for booking {request.booking_id}'
                    )

                    # Step 4c: Broadcast SSE for real-time UI updates
                    await self.sse_broadcaster.broadcast(
                        booking_id=UUID(request.booking_id),
                        event_data={
                            'event_type': 'booking_updated',
                            'event_id': request.event_id,
                            'booking_id': request.booking_id,
                            'status': 'PENDING_PAYMENT',
                            'tickets': pg_result.get('tickets', []),
                            'subsection_stats': subsection_stats,
                            'event_stats': event_stats,
                        },
                    )

                    return ReservationResult(
                        success=True,
                        booking_id=request.booking_id,
                        reserved_seats=reserved_seats,
                        total_price=total_price,
                        event_id=request.event_id,
                    )
                else:
                    error_msg = result.get('error_message', 'Reservation failed')

                    Logger.base.warning(f'⚠️ [RESERVE] Reservation failed: {error_msg}')

                    # Set error attributes on span
                    span = trace.get_current_span()
                    span.set_status(trace.Status(trace.StatusCode.ERROR, error_msg))
                    span.set_attribute('error', True)
                    span.set_attribute('error.type', 'reservation_failed')
                    span.set_attribute('error.message', error_msg)

                    # Write FAILED booking directly to PostgreSQL
                    await self.booking_command_repo.create_failed_booking_directly(
                        booking_id=request.booking_id,
                        buyer_id=request.buyer_id,
                        event_id=request.event_id,
                        section=request.section_filter or '',
                        subsection=request.subsection_filter or 0,
                        seat_selection_mode=request.selection_mode,
                        seat_positions=request.seat_positions or [],
                        quantity=request.quantity or len(request.seat_positions or []),
                    )

                    # Broadcast SSE failure notification
                    await self.sse_broadcaster.broadcast(
                        booking_id=UUID(request.booking_id),
                        event_data={
                            'event_type': 'booking_updated',
                            'event_id': request.event_id,
                            'booking_id': request.booking_id,
                            'status': 'FAILED',
                            'tickets': [],
                            'error_message': error_msg,
                        },
                    )

                    return ReservationResult(
                        success=False,
                        booking_id=request.booking_id,
                        error_message=error_msg,
                        event_id=request.event_id,
                    )

            except DomainError as e:
                Logger.base.warning(f'⚠️ [RESERVE] Domain error: {e}')
                error_msg = str(e)

                # Record exception on span
                span = trace.get_current_span()
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, error_msg))
                span.set_attribute('error', True)
                span.set_attribute('error.type', 'domain_error')

                # Write FAILED booking directly to PostgreSQL
                await self.booking_command_repo.create_failed_booking_directly(
                    booking_id=request.booking_id,
                    buyer_id=request.buyer_id,
                    event_id=request.event_id,
                    section=request.section_filter or '',
                    subsection=request.subsection_filter or 0,
                    seat_selection_mode=request.selection_mode,
                    seat_positions=request.seat_positions or [],
                    quantity=request.quantity or len(request.seat_positions or []),
                )

                # Broadcast SSE failure notification
                await self.sse_broadcaster.broadcast(
                    booking_id=UUID(request.booking_id),
                    event_data={
                        'event_type': 'booking_updated',
                        'event_id': request.event_id,
                        'booking_id': request.booking_id,
                        'status': 'FAILED',
                        'tickets': [],
                        'error_message': error_msg,
                    },
                )

                return ReservationResult(
                    success=False,
                    booking_id=request.booking_id,
                    error_message=error_msg,
                    event_id=request.event_id,
                )
            except Exception as e:
                Logger.base.exception(f'❌ [RESERVE] Unexpected error: {e}')
                error_msg = 'Internal server error'

                # Record exception on span
                span = trace.get_current_span()
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, error_msg))
                span.set_attribute('error', True)
                span.set_attribute('error.type', 'unexpected_error')

                # Write FAILED booking directly to PostgreSQL
                await self.booking_command_repo.create_failed_booking_directly(
                    booking_id=request.booking_id,
                    buyer_id=request.buyer_id,
                    event_id=request.event_id,
                    section=request.section_filter or '',
                    subsection=request.subsection_filter or 0,
                    seat_selection_mode=request.selection_mode,
                    seat_positions=request.seat_positions or [],
                    quantity=request.quantity or len(request.seat_positions or []),
                )

                # Broadcast SSE failure notification
                await self.sse_broadcaster.broadcast(
                    booking_id=UUID(request.booking_id),
                    event_data={
                        'event_type': 'booking_updated',
                        'event_id': request.event_id,
                        'booking_id': request.booking_id,
                        'status': 'FAILED',
                        'tickets': [],
                        'error_message': error_msg,
                    },
                )

                return ReservationResult(
                    success=False,
                    booking_id=request.booking_id,
                    error_message=error_msg,
                    event_id=request.event_id,
                )

    def _validate_request(self, request: ReservationRequest) -> None:
        if request.selection_mode == 'manual':
            if not request.seat_positions:
                raise DomainError('Manual selection requires seat positions', 400)
            if len(request.seat_positions) > 4:
                raise DomainError('Cannot reserve more than 4 seats at once', 400)

        elif request.selection_mode == 'best_available':
            if not request.quantity or request.quantity <= 0:
                raise DomainError('Best available selection requires valid quantity', 400)
            if request.quantity > 4:
                raise DomainError('Cannot reserve more than 4 seats at once', 400)
            if not request.section_filter or request.subsection_filter < 1:
                raise DomainError('Best available mode requires section and subsection filter', 400)

        else:
            raise DomainError(f'Invalid selection mode: {request.selection_mode}', 400)
