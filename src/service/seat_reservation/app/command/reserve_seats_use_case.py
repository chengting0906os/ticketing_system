"""
Reserve Seats Use Case
座位預訂用例 - 基於 Lua 腳本的原子性操作
"""

from dataclasses import dataclass
from typing import List, Optional

import anyio.abc

from src.platform.exception.exceptions import DomainError
from src.platform.logging.loguru_io import Logger
from src.service.shared_kernel.app.interface import ISeatStateCommandHandler
from src.service.seat_reservation.app.interface.i_seat_reservation_event_publisher import (
    ISeatReservationEventPublisher,
)


@dataclass
class ReservationRequest:
    """座位預訂請求"""

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
    """座位預訂結果"""

    success: bool
    booking_id: str  # Changed to str for UUID7
    reserved_seats: Optional[List[str]] = None
    total_price: int = 0
    error_message: Optional[str] = None
    event_id: Optional[int] = None


class ReserveSeatsUseCase:
    """
    座位預訂用例 - Event-Driven Non-Blocking Flow

    Responsibility: Seat Reservation Service (Kvrocks only)

    Flow:
    1. Reserve seats in Kvrocks (atomic operation, returns prices)
    2. Fire-and-forget: Publish event to Ticketing Service
       → Ticketing Service handles PostgreSQL persistence
    3. Return immediately (non-blocking)

    Design Principles:
    - Single Responsibility: Only manages Kvrocks state
    - Separation of Concerns: Each service manages its own storage
    - Non-blocking: No database I/O in critical path
    - Event-driven: Communication via Kafka events

    Dependencies:
    - seat_state_handler: For Kvrocks seat reservation
    - mq_publisher: For event publishing (fire-and-forget)
    """

    def __init__(
        self,
        seat_state_handler: ISeatStateCommandHandler,
        mq_publisher: ISeatReservationEventPublisher,
        task_group: anyio.abc.TaskGroup,
    ):
        self.seat_state_handler = seat_state_handler
        self.mq_publisher = mq_publisher
        self.task_group = task_group

    @Logger.io
    async def reserve_seats(self, request: ReservationRequest) -> ReservationResult:
        """
        執行座位預訂 - Non-blocking Event-Driven Flow

        Flow:
        1. Validate request
        2. Reserve seats in Kvrocks (atomic operation, returns prices)
        3. Fire-and-forget: Publish event to Ticketing Service
           → Ticketing Service handles PostgreSQL write (Booking + Tickets)
        4. Return immediately (non-blocking)

        Design Rationale:
        - Seat Reservation Service: Only manages Kvrocks state (fast, non-blocking)
        - Ticketing Service: Handles PostgreSQL persistence (via event)
        - Separation of concerns: Each service manages its own storage

        Args:
            request: 預訂請求

        Returns:
            預訂結果 (from Kvrocks only)
        """
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
                quantity=request.quantity if request.selection_mode == 'best_available' else None,
            )

            # Step 3: Handle result
            if result['success']:
                reserved_seats = result['reserved_seats']
                seat_prices = result['seat_prices']
                total_price = result['total_price']

                Logger.base.info(
                    f'✅ [RESERVE] Successfully reserved {len(reserved_seats)} seats '
                    f'in Kvrocks for booking {request.booking_id} (total: {total_price})'
                )

                # Step 4: Fire-and-forget event to Ticketing Service
                # Ticketing Service will handle PostgreSQL write (Booking + Tickets)
                async def _publish_success() -> None:
                    await self.mq_publisher.publish_seats_reserved(
                        booking_id=request.booking_id,
                        buyer_id=request.buyer_id,
                        event_id=request.event_id,
                        section=request.section_filter or '',
                        subsection=request.subsection_filter or 0,
                        seat_selection_mode=request.selection_mode,
                        reserved_seats=reserved_seats,
                        seat_prices=seat_prices,
                        total_price=total_price,
                    )

                self.task_group.start_soon(_publish_success)  # type: ignore[arg-type]
                Logger.base.info(
                    f'📤 [RESERVE] Scheduled seats_reserved event for booking {request.booking_id}'
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

                # Send failure notification (fire-and-forget)
                async def _publish_failed() -> None:
                    await self.mq_publisher.publish_reservation_failed(
                        booking_id=request.booking_id,
                        buyer_id=request.buyer_id,
                        error_message=error_msg,
                        event_id=request.event_id,
                    )

                self.task_group.start_soon(_publish_failed)  # type: ignore[arg-type]

                return ReservationResult(
                    success=False,
                    booking_id=request.booking_id,
                    error_message=error_msg,
                    event_id=request.event_id,
                )

        except DomainError as e:
            Logger.base.warning(f'⚠️ [RESERVE] Domain error: {e}')
            error_msg = str(e)

            # Fire-and-forget error notification
            async def _publish_domain_error() -> None:
                await self.mq_publisher.publish_reservation_failed(
                    booking_id=request.booking_id,
                    buyer_id=request.buyer_id,
                    error_message=error_msg,
                    event_id=request.event_id,
                )

            self.task_group.start_soon(_publish_domain_error)  # type: ignore[arg-type]

            return ReservationResult(
                success=False,
                booking_id=request.booking_id,
                error_message=error_msg,
                event_id=request.event_id,
            )
        except Exception as e:
            Logger.base.error(f'❌ [RESERVE] Unexpected error: {e}')
            error_msg = 'Internal server error'

            # Fire-and-forget error notification
            async def _publish_unexpected_error() -> None:
                await self.mq_publisher.publish_reservation_failed(
                    booking_id=request.booking_id,
                    buyer_id=request.buyer_id,
                    error_message=error_msg,
                    event_id=request.event_id,
                )

            self.task_group.start_soon(_publish_unexpected_error)  # type: ignore[arg-type]

            return ReservationResult(
                success=False,
                booking_id=request.booking_id,
                error_message=error_msg,
                event_id=request.event_id,
            )

    def _validate_request(self, request: ReservationRequest) -> None:
        """驗證預訂請求"""
        if request.selection_mode == 'manual':
            if not request.seat_positions:
                raise DomainError('Manual selection requires seat positions', 400)
            if len(request.seat_positions) > 6:
                raise DomainError('Cannot reserve more than 6 seats at once', 400)

        elif request.selection_mode == 'best_available':
            if not request.quantity or request.quantity <= 0:
                raise DomainError('Best available selection requires valid quantity', 400)
            if request.quantity > 6:
                raise DomainError('Cannot reserve more than 6 seats at once', 400)
            if not request.section_filter or request.subsection_filter is None:
                raise DomainError('Best available mode requires section and subsection filter', 400)

        else:
            raise DomainError(f'Invalid selection mode: {request.selection_mode}', 400)
