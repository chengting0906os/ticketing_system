"""
Reserve Seats Use Case - Atomic operations based on Lua scripts
"""

from opentelemetry import trace

from src.platform.exception.exceptions import DomainError
from src.platform.logging.loguru_io import Logger
from src.service.seat_reservation.app.dto import ReservationRequest, ReservationResult
from src.service.seat_reservation.app.interface.i_event_state_broadcaster import (
    IEventStateBroadcaster,
)
from src.service.seat_reservation.app.interface.i_seat_reservation_event_publisher import (
    ISeatReservationEventPublisher,
)
from src.service.shared_kernel.app.interface import ISeatStateCommandHandler


class ReserveSeatsUseCase:
    """
    Reserve Seats Use Case - Event-Driven Flow

    Responsibility: Seat Reservation Service (Kvrocks only)

    Flow:
    1. Reserve seats in Kvrocks (atomic operation, returns prices)
    2. Publish event to Ticketing Service (Kafka producer is buffered)
       → Ticketing Service handles PostgreSQL persistence
    3. Return result

    Design Principles:
    - Single Responsibility: Only manages Kvrocks state
    - Separation of Concerns: Each service manages its own storage
    - Minimal latency: Kafka producer is buffered/batched
    - Event-driven: Communication via Kafka events

    Dependencies:
    - seat_state_handler: For Kvrocks seat reservation
    - mq_publisher: For Kafka event publishing
    - event_state_broadcaster: For Redis Pub/Sub cache updates
    """

    def __init__(
        self,
        seat_state_handler: ISeatStateCommandHandler,
        mq_publisher: ISeatReservationEventPublisher,
        event_state_broadcaster: IEventStateBroadcaster,
    ):
        self.seat_state_handler = seat_state_handler
        self.mq_publisher = mq_publisher
        self.event_state_broadcaster = event_state_broadcaster
        self.tracer = trace.get_tracer(__name__)

    @Logger.io
    async def reserve_seats(self, request: ReservationRequest) -> ReservationResult:
        """
        Execute seat reservation - Event-Driven Flow

        Flow:
        1. Validate request
        2. Reserve seats in Kvrocks (atomic operation, returns prices)
        3. Publish event to Ticketing Service (Kafka producer is buffered)
           → Ticketing Service handles PostgreSQL write (Booking + Tickets)
        4. Return result

        Design Rationale:
        - Seat Reservation Service: Only manages Kvrocks state (fast)
        - Ticketing Service: Handles PostgreSQL persistence (via event)
        - Separation of concerns: Each service manages its own storage
        - Minimal latency: Kafka producer batches messages

        Args:
            request: Reservation request

        Returns:
            Reservation result (from Kvrocks only)
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

                    # Step 4b: Publish event to Ticketing Service (Kafka - business logic)
                    # Ticketing Service will handle PostgreSQL write (Booking + Tickets)
                    await self.mq_publisher.publish_seats_reserved(
                        booking_id=request.booking_id,
                        buyer_id=request.buyer_id,
                        event_id=request.event_id,
                        section=request.section_filter or '',
                        subsection=request.subsection_filter or 0,
                        seat_selection_mode=request.selection_mode,
                        reserved_seats=reserved_seats,
                        total_price=total_price,
                        subsection_stats=subsection_stats,
                        event_stats=event_stats,
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

                    # Send failure notification with full booking info
                    await self.mq_publisher.publish_reservation_failed(
                        booking_id=request.booking_id,
                        buyer_id=request.buyer_id,
                        event_id=request.event_id,
                        section=request.section_filter or '',
                        subsection=request.subsection_filter or 0,
                        quantity=request.quantity or len(request.seat_positions or []),
                        seat_selection_mode=request.selection_mode,
                        seat_positions=request.seat_positions or [],
                        error_message=error_msg,
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

                # Send error notification with full booking info
                await self.mq_publisher.publish_reservation_failed(
                    booking_id=request.booking_id,
                    buyer_id=request.buyer_id,
                    event_id=request.event_id,
                    section=request.section_filter or '',
                    subsection=request.subsection_filter or 0,
                    quantity=request.quantity or len(request.seat_positions or []),
                    seat_selection_mode=request.selection_mode,
                    seat_positions=request.seat_positions or [],
                    error_message=error_msg,
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

                # Send error notification with full booking info
                await self.mq_publisher.publish_reservation_failed(
                    booking_id=request.booking_id,
                    buyer_id=request.buyer_id,
                    event_id=request.event_id,
                    section=request.section_filter or '',
                    subsection=request.subsection_filter or 0,
                    quantity=request.quantity or len(request.seat_positions or []),
                    seat_selection_mode=request.selection_mode,
                    seat_positions=request.seat_positions or [],
                    error_message=error_msg,
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
