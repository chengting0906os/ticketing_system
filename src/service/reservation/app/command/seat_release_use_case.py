"""
Seat Release Use Case - PostgreSQL First Flow

New 6-Step Flow:
1. Fetch booking from DB
2. Idempotency Check (booking status)
3. Fetch Config (Kvrocks)
4. PostgreSQL Write (booking + tickets)
5. Kvrocks Pipeline (update seat map)
6. SSE broadcast
"""

from typing import TYPE_CHECKING

from opentelemetry import trace

from src.platform.exception.exceptions import DomainError
from src.platform.logging.loguru_io import Logger

if TYPE_CHECKING:
    from src.service.ticketing.domain.entity.booking_entity import Booking
from src.service.reservation.app.dto import (
    ReleaseSeatsBatchRequest,
    ReleaseSeatsBatchResult,
)
from src.service.reservation.app.interface import (
    ISeatingConfigQueryHandler,
    ISeatStateReleaseCommandHandler,
)
from src.service.reservation.app.interface.i_booking_command_repo import (
    IBookingCommandRepo,
)
from src.service.shared_kernel.domain.value_object import BookingStatus
from src.service.shared_kernel.driven_adapter.pubsub_handler_impl import (
    PubSubHandlerImpl,
)


class SeatReleaseUseCase:
    """
    Release Seat Use Case - PostgreSQL First Flow

    New 6-Step Flow:
    1. Validate Request - Check seat_positions exists
    2. Idempotency Check - Query PostgreSQL booking table
    3. Fetch Config - Get seating config from Kvrocks
    4. PostgreSQL Write - Update booking + tickets
    5. Kvrocks Pipeline - Update seat map (BITFIELD SET 0)
    6. SSE Broadcast - Notify users

    Design Principles:
    - PostgreSQL as source of truth for idempotency
    - Pipeline for batch seat map updates
    """

    def __init__(
        self,
        seat_state_handler: ISeatStateReleaseCommandHandler,
        seating_config_handler: ISeatingConfigQueryHandler,
        booking_command_repo: IBookingCommandRepo,
        pubsub_handler: PubSubHandlerImpl,
    ) -> None:
        self.seat_state_handler = seat_state_handler
        self.seating_config_handler = seating_config_handler
        self.booking_command_repo = booking_command_repo
        self.pubsub_handler = pubsub_handler
        self.tracer = trace.get_tracer(__name__)

    @Logger.io
    async def execute_batch(self, request: ReleaseSeatsBatchRequest) -> ReleaseSeatsBatchResult:
        """
        Execute seat release - PostgreSQL First Flow

        New 6-Step Flow:
        1. Fetch booking from DB (all details needed)
        2. Idempotency Check (booking status)
        3. Fetch Config (Kvrocks)
        4. PostgreSQL Write (booking + tickets)
        5. Kvrocks Pipeline (update seat map)
        6. SSE Broadcast
        """
        with self.tracer.start_as_current_span(
            'use_case.release_seats',
            attributes={
                'booking.id': request.booking_id,
                'event.id': request.event_id,
            },
        ):
            try:
                # ========== Step 1: Fetch Booking from DB ==========
                booking = await self.booking_command_repo.get_by_id(booking_id=request.booking_id)
                if not booking:
                    error_msg = f'Booking {request.booking_id} not found'
                    Logger.base.warning(f'[RELEASE] {error_msg}')
                    return self._error_result(error_msg)

                Logger.base.info(
                    f'[RELEASE] Processing release for booking {request.booking_id}, '
                    f'buyer {booking.buyer_id}, {len(booking.seat_positions or [])} seats'
                )

                # ========== Step 2: Idempotency Check ==========
                if booking.status == BookingStatus.CANCELLED:
                    Logger.base.info(
                        f'[IDEMPOTENCY] Booking {request.booking_id} already cancelled, '
                        'completing remaining steps'
                    )
                    return await self._complete_success_flow(booking=booking)

                if booking.status != BookingStatus.PENDING_PAYMENT:
                    error_msg = f'Booking {request.booking_id} not in PENDING_PAYMENT status'
                    Logger.base.warning(f'[RELEASE] {error_msg}')
                    return self._error_result(error_msg)

                # ========== Step 3: PostgreSQL Write ==========
                await self.booking_command_repo.update_status_to_cancelled_and_release_tickets(
                    booking_id=request.booking_id
                )
                Logger.base.info(
                    f'[RELEASE] PostgreSQL write complete for booking {request.booking_id}'
                )

                # ========== Step 4 + 5: Kvrocks + SSE ==========
                return await self._complete_success_flow(booking=booking)

            except DomainError as e:
                Logger.base.warning(f'[RELEASE] Domain error: {e}')
                return self._error_result(str(e))

            except Exception as e:
                Logger.base.exception(f'[RELEASE] Unexpected error: {e}')
                return self._error_result('Internal server error')

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

    async def _complete_success_flow(self, *, booking: 'Booking') -> ReleaseSeatsBatchResult:
        """Complete Step 4 (Kvrocks) + Step 5 (SSE) + return success result.

        Uses booking entity for all required data (section, subsection, seat_positions, buyer_id).
        """
        seat_positions = booking.seat_positions or []

        # Fetch config for seat index calculation
        try:
            config = await self.seating_config_handler.get_config(
                event_id=booking.event_id,
                section=booking.section,
            )
            cols = config.cols
        except Exception as e:
            error_msg = f'Failed to fetch config: {e}'
            return ReleaseSeatsBatchResult(
                successful_seats=[],
                failed_seats=seat_positions,
                total_released=0,
                error_messages={seat: error_msg for seat in seat_positions},
            )

        seats_to_release = self._build_seats_to_release(seat_positions=seat_positions, cols=cols)

        # Step 4: Kvrocks Pipeline (idempotent - SET 0 when already 0 is no-op)
        await self.seat_state_handler.update_seat_map_release(
            event_id=booking.event_id,
            section=booking.section,
            subsection=booking.subsection,
            booking_id=str(booking.id),
            seats_to_release=seats_to_release,
        )
        Logger.base.info(f'[RELEASE] Kvrocks seat map updated for booking {booking.id}')

        # Step 5: SSE Broadcast
        await self.pubsub_handler.schedule_stats_broadcast(event_id=booking.event_id)
        await self.pubsub_handler.publish_booking_update(
            user_id=booking.buyer_id,
            event_id=booking.event_id,
            event_data={
                'event_type': 'booking_updated',
                'event_id': booking.event_id,
                'booking_id': str(booking.id),
                'status': BookingStatus.CANCELLED,
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
    def _error_result(error_msg: str) -> ReleaseSeatsBatchResult:
        return ReleaseSeatsBatchResult(
            successful_seats=[],
            failed_seats=[],
            total_released=0,
            error_messages={'booking': error_msg},
        )
