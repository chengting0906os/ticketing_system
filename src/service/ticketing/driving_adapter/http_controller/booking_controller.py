import json
from typing import List
from uuid import UUID

import anyio
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status
from opentelemetry import trace
from sse_starlette.sse import EventSourceResponse

from src.platform.config.di import Container
from src.platform.logging.loguru_io import Logger
from src.service.ticketing.driven_adapter.sse import sse_broadcaster
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
from src.service.ticketing.driving_adapter.schema.booking_schema import (
    BookingCreateRequest,
    BookingDetailResponse,
    BookingResponse,
    BookingWithDetailsResponse,
    CancelReservationResponse,
    PaymentRequest,
    PaymentResponse,
)


router = APIRouter()


@router.get('/my_booking', response_model=List[BookingWithDetailsResponse])
@Logger.io
@inject
async def list_my_bookings(
    booking_status: str = '',
    current_user: UserEntity = Depends(get_current_user),
    use_case: ListBookingsUseCase = Depends(Provide[Container.list_bookings_use_case]),
):
    if not current_user.id:
        raise HTTPException(status_code=400, detail='User ID is required')

    if RoleAuthStrategy.is_buyer(current_user):
        return await use_case.list_buyer_bookings(current_user.id, booking_status)
    elif RoleAuthStrategy.is_seller(current_user):
        return await use_case.list_seller_bookings(current_user.id, booking_status)
    else:
        return []


@router.post('', status_code=status.HTTP_201_CREATED)
@inject
async def create_booking(
    request: BookingCreateRequest,
    current_user: UserEntity = Depends(require_buyer),
    booking_use_case: CreateBookingUseCase = Depends(Provide[Container.create_booking_use_case]),
) -> BookingResponse:
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(
        'controller.create_booking',
        attributes={
            'http.method': 'POST',
            'http.route': '/api/booking',
            'event_id': str(request.event_id),
            'section': request.section,
            'subsection': request.subsection,
            'quantity': request.quantity,
        },
    ):
        if not current_user.id:
            raise HTTPException(status_code=400, detail='User ID is required')

        # Create booking - ticket validation and reservation are now handled atomically inside use case
        booking = await booking_use_case.create_booking(
            buyer_id=current_user.id,
            event_id=request.event_id,
            section=request.section,
            subsection=request.subsection,
            seat_selection_mode=request.seat_selection_mode,
            seat_positions=request.seat_positions,
            quantity=request.quantity,
        )

        with tracer.start_as_current_span('controller.build_response'):
            return BookingResponse.model_validate(
                {
                    'id': str(booking.id) if booking.id else None,
                    'buyer_id': str(booking.buyer_id),
                    'event_id': str(booking.event_id),
                    'total_price': booking.total_price,
                    'status': booking.status.value,
                    'created_at': booking.created_at,
                },
                strict=False,
            )


@router.get('/{booking_id}')
@Logger.io
@inject
async def get_booking(
    booking_id: UUID,
    current_user: UserEntity = Depends(get_current_user),
    use_case: GetBookingUseCase = Depends(Provide[Container.get_booking_use_case]),
) -> BookingDetailResponse:
    booking_details = await use_case.get_booking_with_details(booking_id)
    return BookingDetailResponse(**booking_details)


@router.patch('/{booking_id}', status_code=status.HTTP_200_OK)
@Logger.io
@inject
async def cancel_booking(
    booking_id: UUID,
    current_user: UserEntity = Depends(require_buyer),
    use_case: UpdateBookingToCancelledUseCase = Depends(
        Provide[Container.update_booking_to_cancelled_use_case]
    ),
):
    if not current_user.id:
        raise HTTPException(status_code=400, detail='User ID is required')

    # Use case will raise exceptions for validation errors (Fail Fast)
    booking = await use_case.execute(
        booking_id=booking_id,
        buyer_id=current_user.id,
    )
    return CancelReservationResponse(
        status=booking.status.value,
        cancelled_tickets=booking.quantity,
    )


@router.post('/{booking_id}/pay')
@Logger.io
@inject
async def pay_booking(
    booking_id: UUID,
    request: PaymentRequest,
    current_user: UserEntity = Depends(require_buyer),
    use_case: MockPaymentAndUpdateBookingStatusToCompletedAndTicketToPaidUseCase = Depends(
        Provide[Container.mock_payment_use_case]
    ),
) -> PaymentResponse:
    if not current_user.id:
        raise HTTPException(status_code=400, detail='User ID is required')

    result = await use_case.pay_booking(
        booking_id=booking_id, buyer_id=current_user.id, card_number=request.card_number
    )

    return PaymentResponse(
        booking_id=result['booking_id'],
        payment_id=result['payment_id'],
        status=result['status'],
        paid_at=result['paid_at'],
    )


# ============================ SSE Endpoint ============================


@router.get('/{booking_id}/status/sse', status_code=status.HTTP_200_OK)
@Logger.io
@inject
async def stream_booking_status(
    booking_id: UUID,
    current_user: UserEntity = Depends(get_current_user),
    booking_query_use_case: GetBookingUseCase = Depends(Provide[Container.get_booking_use_case]),
):
    """
    SSE real-time booking status updates

    Architecture: Event-Driven SSE (Kafka notification → SSE Manager → Client)

    Flow:
    1. Client connects → Query current booking status (initial_status)
    2. Subscribe to SSE Manager for this booking_id
    3. Wait for Kafka notifications → SSE Manager broadcasts → Push to client

    Event Types:
    - initial_status: First event with current booking state
    - seats_reserved: Seats successfully reserved (PENDING_PAYMENT)
    - booking_failed: Reservation failed (FAILED)
    - payment_completed: Payment successful (COMPLETED)
    - booking_cancelled: Booking cancelled (CANCELLED)

    Returns:
        EventSourceResponse with booking status updates

    Raises:
        HTTPException 403: If user doesn't own this booking
        HTTPException 404: If booking not found
    """
    # Verify booking exists and user owns it
    try:
        booking = await booking_query_use_case.get_booking(booking_id=booking_id)
    except Exception as e:
        Logger.base.warning(f'❌ [SSE] Booking {booking_id} not found: {e}')
        raise HTTPException(status_code=404, detail='Booking not found')

    # Authorization: Only booking owner can access SSE stream
    if not current_user.id:
        raise HTTPException(status_code=401, detail='Unauthorized')

    if booking.buyer_id != current_user.id:
        Logger.base.warning(
            f'⛔ [SSE] User {current_user.id} attempted to access booking {booking_id} '
            f'(owner: {booking.buyer_id})'
        )
        raise HTTPException(status_code=403, detail='Forbidden')

    async def event_generator():
        """Generate SSE events for booking status changes"""
        queue = None

        try:
            # Subscribe to SSE broadcaster
            queue = await sse_broadcaster.subscribe(booking_id=booking_id)

            Logger.base.info(
                f'📡 [SSE] User {current_user.id} connected to booking {booking_id} stream'
            )

            # Send initial status event
            initial_event = {
                'event_type': 'initial_status',
                'booking_id': str(booking_id),
                'status': booking.status.value,
                'created_at': booking.created_at.isoformat() if booking.created_at else None,
                'total_price': booking.total_price,
                'seat_positions': booking.seat_positions or [],
            }
            yield {'event': 'initial_status', 'data': json.dumps(initial_event)}

            # Listen for status updates
            while True:
                try:
                    # Wait for next event from SSE manager
                    update = await queue.get()

                    # Check for close sentinel
                    if update.get('event_type') == '_close':
                        Logger.base.info(f'📡 [SSE] Close signal received for booking {booking_id}')
                        break

                    # Send status update to client
                    event_type = update.get('event_type', 'status_update')
                    yield {'event': event_type, 'data': json.dumps(update)}

                except anyio.get_cancelled_exc_class():
                    Logger.base.info(f'🔌 [SSE] Client disconnected from booking {booking_id}')
                    break
                except Exception as e:
                    Logger.base.error(
                        f'❌ [SSE] Error in event stream for booking {booking_id}: {e}'
                    )
                    # Send error to client
                    error_event = {
                        'event_type': 'error',
                        'error': str(e),
                    }
                    yield {'event': 'error', 'data': json.dumps(error_event)}
                    break

        except anyio.get_cancelled_exc_class():
            Logger.base.info(f'🔌 [SSE] Connection cancelled for booking {booking_id}')
        except Exception as e:
            Logger.base.error(f'💥 [SSE] Fatal error for booking {booking_id}: {e}')
        finally:
            # Unsubscribe from SSE broadcaster
            if queue:
                await sse_broadcaster.unsubscribe(booking_id=booking_id)
            Logger.base.info(f'🧹 [SSE] Cleanup completed for booking {booking_id}')

    return EventSourceResponse(event_generator())
