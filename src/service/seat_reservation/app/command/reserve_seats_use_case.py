"""
Reserve Seats Use Case - Atomic operations based on Lua scripts
"""

from dataclasses import dataclass
from typing import List, Optional

from opentelemetry import trace

from src.platform.exception.exceptions import DomainError
from src.platform.logging.loguru_io import Logger
from src.service.seat_reservation.app.interface.i_seat_reservation_event_publisher import (
    ISeatReservationEventPublisher,
)
from src.service.shared_kernel.app.interface import ISeatStateCommandHandler


@dataclass
class ReservationRequest:
    """Seat reservation request"""

    booking_id: str  # Changed to str for UUID7
    buyer_id: int
    event_id: int
    selection_mode: str  # 'manual' or 'best_available'
    quantity: Optional[int] = None
    seat_positions: Optional[List[str]] = None  # Manually selected seat IDs
    section_filter: Optional[str] = None
    subsection_filter: Optional[int] = None


@dataclass
class ReservationResult:
    """Seat reservation result"""

    success: bool
    booking_id: str  # Changed to str for UUID7
    reserved_seats: Optional[List[str]] = None
    total_price: int = 0
    error_message: Optional[str] = None
    event_id: Optional[int] = None


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
    - mq_publisher: For event publishing
    """

    def __init__(
        self,
        seat_state_handler: ISeatStateCommandHandler,
        mq_publisher: ISeatReservationEventPublisher,
    ):
        self.seat_state_handler = seat_state_handler
        self.mq_publisher = mq_publisher
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
                result = await self.seat_state_handler.reserve_seats_atomic(
                    event_id=request.event_id,
                    booking_id=request.booking_id,
                    buyer_id=request.buyer_id,
                    mode=request.selection_mode,
                    seat_ids=request.seat_positions if request.selection_mode == 'manual' else None,
                    section=request.section_filter,
                    subsection=request.subsection_filter,
                    quantity=request.quantity
                    if request.selection_mode == 'best_available'
                    else None,
                )

                # Step 3: Handle result
                if result['success']:
                    reserved_seats = result['reserved_seats']
                    total_price = result['total_price']
                    subsection_stats = result.get('subsection_stats', {})
                    event_stats = result.get('event_stats', {})
                    event_state = result.get('event_state', {})

                    Logger.base.info(
                        f'✅ [RESERVE] Successfully reserved {len(reserved_seats)} seats '
                        f'in Kvrocks for booking {request.booking_id} (total: {total_price})'
                        f'{" 🎉 SUBSECTION SOLD OUT!" if subsection_stats.get("available", 1) == 0 else ""}'
                        f'{" 🎊 EVENT SOLD OUT!" if event_stats.get("available", 1) == 0 else ""}'
                    )

                    # Step 4: Publish event to Ticketing Service (Kafka producer is buffered)
                    # Ticketing Service will handle PostgreSQL write (Booking + Tickets)
                    # ✨ NEW: Passing entire event_state for full cache update
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
                        event_state=event_state,  # ✨ NEW: Full config
                    )
                    Logger.base.info(
                        f'📤 [RESERVE] Published seats_reserved event for booking {request.booking_id}'
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
                Logger.base.error(f'❌ [RESERVE] Unexpected error: {e}')
                error_msg = 'Internal server error'

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
        """Validate reservation request"""
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
            if not request.section_filter or request.subsection_filter is None:
                raise DomainError('Best available mode requires section and subsection filter', 400)

        else:
            raise DomainError(f'Invalid selection mode: {request.selection_mode}', 400)
