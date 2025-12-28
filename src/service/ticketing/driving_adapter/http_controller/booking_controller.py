from collections.abc import AsyncIterator
from typing import Any, List

import anyio
from fastapi import APIRouter, Depends, HTTPException, status
from opentelemetry import trace
import orjson
from sse_starlette.sse import EventSourceResponse

from src.platform.config.di import container
from src.platform.logging.loguru_io import Logger
from src.platform.types import UtilsUUID7
from src.service.ticketing.app.command.create_booking_use_case import CreateBookingUseCase
from src.service.ticketing.app.command.mock_payment_and_update_booking_status_to_completed_and_ticket_to_paid_use_case import (
    MockPaymentAndUpdateBookingStatusToCompletedAndTicketToPaidUseCase,
)
from src.service.ticketing.app.command.update_booking_status_to_cancelled_use_case import (
    UpdateBookingToCancelledUseCase,
)
from src.service.ticketing.app.query.get_booking_use_case import GetBookingUseCase
from src.service.ticketing.app.query.list_bookings_use_case import ListBookingsUseCase
from src.service.ticketing.domain.entity.user_entity import UserEntity
from src.service.ticketing.driving_adapter.http_controller.auth.role_auth import (
    RoleAuthStrategy,
    get_current_user,
    require_buyer,
)
from src.service.ticketing.driving_adapter.http_controller.schema.booking_schema import (
    BookingCreateRequest,
    BookingDetailResponse,
    BookingResponse,
    BookingWithDetailsResponse,
    CancelReservationResponse,
    PaymentRequest,
    PaymentResponse,
)


router = APIRouter()
tracer = trace.get_tracer(__name__)


@router.get('/my_booking', response_model=List[BookingWithDetailsResponse])
@Logger.io
async def list_my_bookings(
    booking_status: str = '',
    current_user: UserEntity = Depends(get_current_user),
    use_case: ListBookingsUseCase = Depends(ListBookingsUseCase.depends),
) -> list[dict[str, Any]]:
    """List bookings for current user (buyer sees own, seller sees events' bookings)."""
    if RoleAuthStrategy.is_buyer(current_user):
        return await use_case.list_buyer_bookings(current_user.id or 0, booking_status)
    elif RoleAuthStrategy.is_seller(current_user):
        return await use_case.list_seller_bookings(current_user.id or 0, booking_status)
    else:
        return []


@router.post('', status_code=status.HTTP_202_ACCEPTED)
@Logger.io
async def create_booking(
    request: BookingCreateRequest,
    current_user: UserEntity = Depends(require_buyer),
    booking_use_case: CreateBookingUseCase = Depends(CreateBookingUseCase.depends),
) -> BookingResponse:
    with tracer.start_as_current_span('controller.create_booking') as span:
        span.set_attribute('event_id', request.event_id)
        span.set_attribute('section', request.section)
        span.set_attribute('subsection', request.subsection)
        span.set_attribute('buyer_id', current_user.id or 0)

        # Create booking - ticket validation and reservation are now handled atomically inside use case
        booking = await booking_use_case.create_booking(
            buyer_id=current_user.id or 0,
            event_id=request.event_id,
            section=request.section,
            subsection=request.subsection,
            seat_selection_mode=request.seat_selection_mode,
            seat_positions=request.seat_positions,
            quantity=request.quantity,
        )

        if booking.id is None:
            raise ValueError('Booking ID should not be None after creation.')

        span.set_attribute('booking.id', str(booking.id))

        return BookingResponse(
            id=booking.id,
            buyer_id=booking.buyer_id,
            event_id=booking.event_id,
            total_price=booking.total_price,
            status=booking.status.value,  # Should be 'pending_payment' now
            created_at=booking.created_at,
        )


@router.get('/{booking_id}')
@Logger.io
async def get_booking(
    booking_id: UtilsUUID7,
    current_user: UserEntity = Depends(get_current_user),
    use_case: GetBookingUseCase = Depends(GetBookingUseCase.depends),
) -> BookingDetailResponse:
    booking_details = await use_case.get_booking_with_details(booking_id)
    return BookingDetailResponse(**booking_details)


@router.patch('/{booking_id}', status_code=status.HTTP_200_OK)
@Logger.io
async def cancel_booking(
    booking_id: UtilsUUID7,
    current_user: UserEntity = Depends(require_buyer),
    use_case: UpdateBookingToCancelledUseCase = Depends(UpdateBookingToCancelledUseCase.depends),
) -> CancelReservationResponse:
    # Use case will raise exceptions for validation errors (Fail Fast)
    booking = await use_case.execute(
        booking_id=booking_id,
        buyer_id=current_user.id or 0,
    )
    return CancelReservationResponse(
        status=booking.status.value,
        cancelled_tickets=booking.quantity,
    )


@router.post('/{booking_id}/pay')
@Logger.io
async def pay_booking(
    booking_id: UtilsUUID7,
    request: PaymentRequest,
    current_user: UserEntity = Depends(require_buyer),
    use_case: MockPaymentAndUpdateBookingStatusToCompletedAndTicketToPaidUseCase = Depends(
        MockPaymentAndUpdateBookingStatusToCompletedAndTicketToPaidUseCase.depends
    ),
) -> PaymentResponse:
    result = await use_case.pay_booking(
        booking_id=booking_id, buyer_id=current_user.id or 0, card_number=request.card_number
    )

    return PaymentResponse(
        booking_id=result['booking_id'],
        payment_id=result['payment_id'],
        status=result['status'],
        paid_at=result['paid_at'],
    )


# ============================ SSE Endpoint ============================


@router.get('/event/{event_id}/sse', status_code=status.HTTP_200_OK)
@Logger.io
async def stream_booking_status(
    event_id: int,
    current_user: UserEntity = Depends(get_current_user),
) -> EventSourceResponse:
    """
    SSE real-time booking status updates for user's bookings of an event

    Architecture: Use Case → Kvrocks Pub/Sub → SSE Endpoint → Client

    Flow:
    1. Client connects → SSE endpoint subscribes to Kvrocks channel
    2. Updates pushed from reservation service via Kvrocks pub/sub (<100ms latency)
    3. Auto-close when booking reaches final state (completed/failed/cancelled)

    Channel: booking:status:{user_id}:{event_id}
    """
    pubsub_handler = container.pubsub_handler()
    raw_user_id = current_user.id
    if raw_user_id is None:
        raise HTTPException(status_code=401, detail='User ID not found')
    user_id: int = raw_user_id  # Capture narrowed type for closure
    Logger.base.info(f'📡 [SSE] Client subscribing to user={user_id}, event={event_id}')

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        """Generate SSE event stream for booking status updates via Kvrocks pub/sub"""
        final_states = {'completed', 'failed', 'cancelled'}

        try:
            # Subscribe to Kvrocks pub/sub channel
            async for event_data in pubsub_handler.subscribe(
                user_id=user_id,
                event_id=event_id,
            ):
                # Send SSE event
                yield {'event': 'status_update', 'data': orjson.dumps(event_data).decode()}

                Logger.base.debug(
                    f'📡 [SSE] Sent event: user={user_id}, event={event_id}, '
                    f'booking={event_data.get("booking_id")}, status={event_data.get("status")}'
                )

                # Auto-close connection if booking reaches final state
                if event_data.get('status') in final_states:
                    Logger.base.info(
                        f'✅ [SSE] Booking reached final state: {event_data.get("status")}'
                    )
                    yield {
                        'event': 'close',
                        'data': orjson.dumps(
                            {'message': f'Booking reached final state: {event_data.get("status")}'}
                        ).decode(),
                    }
                    break

        except anyio.get_cancelled_exc_class():
            Logger.base.info(f'🔌 [SSE] Client disconnected: user={user_id}, event={event_id}')
            raise
        except Exception as e:
            Logger.base.error(
                f'[SSE] Error in generator for user={user_id}, event={event_id}: {type(e).__name__}: {e}'
            )
            raise

    return EventSourceResponse(event_generator())
