"""
Seat Reservation Use Case - PostgreSQL First Flow

New 6-Step Flow:
1. Validate Request
2. Idempotency Check (PostgreSQL)
3. Lua Script (find/verify seats)
4. PostgreSQL write (booking + tickets)
5. Kvrocks Pipeline (update seat map)
6. SSE broadcast
"""

import attrs
from opentelemetry import trace

from src.platform.exception.exceptions import DomainError
from src.platform.logging.loguru_io import Logger
from src.service.reservation.app.dto import ReservationRequest, ReservationResult
from src.service.reservation.app.interface import ISeatStateCommandHandler
from src.service.reservation.app.interface.i_booking_command_repo import (
    IBookingCommandRepo,
)
from src.service.shared_kernel.domain.value_object import SelectionMode
from src.service.shared_kernel.driven_adapter.pubsub_handler_impl import (
    PubSubHandlerImpl,
)


class SeatReservationUseCase:
    """
    Reserve Seats Use Case - PostgreSQL First Flow

    New 6-Step Flow:
    1. Validate Request - Check seat_positions/quantity <= 4
    2. Idempotency Check - Query PostgreSQL booking table
    3. Lua Script - Find/verify seats in Kvrocks
    4. PostgreSQL Write - Insert booking + update tickets
    5. Kvrocks Pipeline - Update seat map (BITFIELD SET)
    6. SSE Broadcast - Notify users

    Design Principles:
    - PostgreSQL as source of truth for idempotency
    - Lua for read-only seat finding
    - Pipeline for batch seat map updates
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
    async def reserve_seats(self, request: ReservationRequest) -> ReservationResult:
        """
        Execute seat reservation - PostgreSQL First Flow

        New 6-Step Flow:
        1. Validate Request
        2. Idempotency Check (PostgreSQL)
        3. Lua Script (find/verify seats)
        4. PostgreSQL Write (booking + tickets)
        5. Kvrocks Pipeline (update seat map)
        6. SSE Broadcast
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

                # ========== Step 1: Validate Request ==========
                self._validate_request(request)

                # ========== Step 2: Idempotency Check (PostgreSQL) ==========
                existing_booking = await self.booking_command_repo.get_by_id(
                    booking_id=request.booking_id
                )
                if existing_booking and existing_booking.status == 'FAILED':
                    return await self._handle_failure(
                        request, 'Booking previously failed', skip_create=True
                    )
                elif existing_booking and existing_booking.status == 'PENDING_PAYMENT':
                    Logger.base.info(
                        f'✅ [IDEMPOTENCY] Booking {request.booking_id} already exists, '
                        'completing remaining steps'
                    )
                    tickets = await self.booking_command_repo.get_tickets_by_booking_id(
                        booking_id=request.booking_id
                    )
                    return await self._complete_success_flow(
                        request=request,
                        seat_positions=existing_booking.seat_positions,
                        total_price=existing_booking.total_price,
                        tickets_data=[
                            attrs.asdict(t) if attrs.has(type(t)) else t for t in tickets
                        ],
                    )

                # ========== Step 3: Lua Script (find/verify seats) ==========
                if request.selection_mode == SelectionMode.BEST_AVAILABLE:
                    find_result = await self.seat_state_handler.find_seats(
                        event_id=request.event_id,
                        section=request.section_filter,
                        subsection=request.subsection_filter,
                        quantity=request.quantity,
                        rows=request.config.rows if request.config else 0,
                        cols=request.config.cols if request.config else 0,
                        price=request.config.price if request.config else 0,
                    )
                else:  # MANUAL mode (seat_positions validated in _validate_request)
                    find_result = await self.seat_state_handler.verify_seats(
                        event_id=request.event_id,
                        section=request.section_filter,
                        subsection=request.subsection_filter,
                        seat_ids=request.seat_positions or [],
                        price=request.config.price if request.config else 0,
                    )

                if not find_result['success']:
                    error_msg = find_result.get('error_message', 'Seat finding failed')
                    return await self._handle_failure(request, error_msg)

                seats_to_reserve = find_result['seats_to_reserve']
                total_price = find_result['total_price']
                seat_positions = [seat_id for _, _, _, seat_id in seats_to_reserve]

                # ========== Step 4: PostgreSQL Write (booking + tickets) ==========
                pg_result = (
                    await self.booking_command_repo.create_booking_and_update_tickets_to_reserved(
                        booking_id=request.booking_id,
                        buyer_id=request.buyer_id,
                        event_id=request.event_id,
                        section=request.section_filter or '',
                        subsection=request.subsection_filter or 0,
                        seat_selection_mode=request.selection_mode,
                        reserved_seats=seat_positions,
                        total_price=total_price,
                    )
                )
                Logger.base.info(
                    f'✅ [RESERVE] PostgreSQL write complete for booking {request.booking_id}'
                )

                # ========== Step 5 + 6: Kvrocks + SSE ==========

                return await self._complete_success_flow(
                    request=request,
                    seat_positions=seat_positions,
                    total_price=total_price,
                    tickets_data=[
                        attrs.asdict(t) if attrs.has(type(t)) else t
                        for t in pg_result.get('tickets', [])
                    ],
                )

            except DomainError as e:
                Logger.base.warning(f'⚠️ [RESERVE] Domain error: {e}')
                return await self._handle_failure(request, str(e))

            except Exception as e:
                Logger.base.exception(f'❌ [RESERVE] Unexpected error: {e}')
                return await self._handle_failure(request, 'Internal server error')

    def _build_seats_to_reserve(
        self, *, seat_positions: list[str], cols: int
    ) -> list[tuple[int, int, int, str]]:
        """Build seats_to_reserve tuples for Kvrocks update."""
        return [
            (
                int(seat_id.split('-')[0]),
                int(seat_id.split('-')[1]),
                (int(seat_id.split('-')[0]) - 1) * cols + (int(seat_id.split('-')[1]) - 1),
                seat_id,
            )
            for seat_id in seat_positions
        ]

    async def _complete_success_flow(
        self,
        *,
        request: ReservationRequest,
        seat_positions: list[str],
        total_price: int,
        tickets_data: list,
    ) -> ReservationResult:
        """Complete Step 5 (Kvrocks) + Step 6 (SSE) + return success result."""
        if not request.config:
            raise DomainError(f'Missing config for booking {request.booking_id}')

        seats_to_reserve = self._build_seats_to_reserve(
            seat_positions=seat_positions, cols=request.config.cols
        )

        # Step 5: Kvrocks Pipeline (idempotent - SET 1 when already 1 is no-op)
        await self.seat_state_handler.update_seat_map(
            event_id=request.event_id,
            section=request.section_filter,
            subsection=request.subsection_filter,
            booking_id=request.booking_id,
            seats_to_reserve=seats_to_reserve,
            total_price=total_price,
        )
        Logger.base.info(f'✅ [RESERVE] Kvrocks seat map updated for booking {request.booking_id}')

        # Step 6: SSE Broadcast
        await self.pubsub_handler.schedule_stats_broadcast(event_id=request.event_id)
        await self.pubsub_handler.publish_booking_update(
            user_id=request.buyer_id,
            event_id=request.event_id,
            event_data={
                'event_type': 'booking_updated',
                'event_id': request.event_id,
                'booking_id': request.booking_id,
                'status': 'PENDING_PAYMENT',
                'tickets': tickets_data,
            },
        )

        return ReservationResult(
            success=True,
            booking_id=request.booking_id,
            reserved_seats=seat_positions,
            total_price=total_price,
            event_id=request.event_id,
        )

    async def _handle_failure(
        self, request: ReservationRequest, error_msg: str, *, skip_create: bool = False
    ) -> ReservationResult:
        """Handle reservation failure - write FAILED booking and notify via SSE."""
        span = trace.get_current_span()
        span.set_status(trace.Status(trace.StatusCode.ERROR, error_msg))
        span.set_attribute('error', True)
        span.set_attribute('error.message', error_msg)

        # Write FAILED booking to PostgreSQL (skip if already exists)
        if not skip_create:
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

        # Publish SSE failure notification
        await self.pubsub_handler.publish_booking_update(
            user_id=request.buyer_id,
            event_id=request.event_id,
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
        if request.selection_mode == SelectionMode.MANUAL:
            if not request.seat_positions:
                raise DomainError('Manual selection requires seat positions')
            if len(request.seat_positions) > 4:
                raise DomainError('Cannot reserve more than 4 seats at once')

        elif request.selection_mode == SelectionMode.BEST_AVAILABLE:
            if not request.quantity or request.quantity <= 0:
                raise DomainError('Best available selection requires valid quantity')
            if request.quantity > 4:
                raise DomainError('Cannot reserve more than 4 seats at once')
            if not request.section_filter or request.subsection_filter < 1:
                raise DomainError('Best available mode requires section and subsection filter')

        else:
            raise DomainError(f'Invalid selection mode: {request.selection_mode}')
