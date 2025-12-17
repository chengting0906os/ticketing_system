import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any, List

import anyio
from fastapi import APIRouter, Depends, status
from opentelemetry import trace
import orjson
from sse_starlette.sse import EventSourceResponse

from src.platform.logging.loguru_io import Logger
from src.platform.state import kvrocks_client
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


@router.post('', status_code=status.HTTP_201_CREATED)
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


# ============================ SSE Endpoint (Redis Pub/Sub) ============================


@router.get('/subscribe/{event_id}/sse', status_code=status.HTTP_200_OK)
@Logger.io
async def stream_booking_result(
    event_id: int,
    current_user: UserEntity = Depends(require_buyer),
) -> EventSourceResponse:
    """
    SSE endpoint for pre-booking subscription via Redis Pub/Sub

    Client subscribes BEFORE creating booking:
    1. Client opens SSE connection: GET /booking/subscribe/{event_id}/sse
    2. Client creates booking: POST /booking
    3. Reservation service publishes result to Redis Pub/Sub
    4. This endpoint receives and pushes to client

    Architecture:
    - Ticketing Service: SSE endpoint subscribes to Redis channel
    - Reservation Service: Publishes booking result to Redis channel

    Channel format: booking_result:{buyer_id}:{event_id}
    """
    buyer_id = current_user.id or 0
    channel = f'booking_result:{buyer_id}:{event_id}'

    Logger.base.info(f'📡 [SSE] Client subscribing to Redis channel: {channel}')

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        """Generate SSE event stream from Redis Pub/Sub"""
        final_states = {'PENDING_PAYMENT', 'FAILED', 'CANCELLED'}
        pubsub = None

        try:
            # Subscribe to Redis channel
            client = kvrocks_client.get_client()
            pubsub = client.pubsub()
            await pubsub.subscribe(channel)

            Logger.base.info(f'📡 [SSE] Subscribed to Redis channel: {channel}')

            # Send initial connection confirmation
            yield {
                'event': 'connected',
                'data': orjson.dumps(
                    {
                        'event_type': 'connected',
                        'buyer_id': buyer_id,
                        'event_id': event_id,
                        'message': 'Waiting for booking result...',
                    }
                ).decode(),
            }

            # Event-driven loop: wait for messages from Redis Pub/Sub
            while True:
                try:
                    # Wait for message with timeout (60s for heartbeat)
                    message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                        timeout=60.0,
                    )

                    if message is not None and message['type'] == 'message':
                        # Parse message data
                        data = orjson.loads(message['data'])

                        # Send booking result to client
                        yield {'event': 'booking_result', 'data': orjson.dumps(data).decode()}

                        Logger.base.info(
                            f'📡 [SSE] Sent result: buyer={buyer_id}, event={event_id}, '
                            f'booking={data.get("booking_id")}, status={data.get("status")}'
                        )

                        # Auto-close if booking reaches final state
                        if data.get('status') in final_states:
                            Logger.base.info(
                                f'✅ [SSE] Booking complete: buyer={buyer_id}, event={event_id}'
                            )
                            yield {
                                'event': 'close',
                                'data': orjson.dumps(
                                    {
                                        'message': f'Booking {data.get("status")}',
                                        'booking_id': data.get('booking_id'),
                                    }
                                ).decode(),
                            }
                            break

                except asyncio.TimeoutError:
                    # Heartbeat to prevent connection timeout
                    yield {
                        'event': 'heartbeat',
                        'data': orjson.dumps(
                            {
                                'timestamp': datetime.now(timezone.utc).isoformat(),
                            }
                        ).decode(),
                    }

                except Exception as e:
                    Logger.base.error(f'❌ [SSE] Error: buyer={buyer_id}, event={event_id}: {e}')
                    yield {'data': orjson.dumps({'error': str(e)}).decode()}
                    break

        except anyio.get_cancelled_exc_class():
            # Client disconnected - don't re-raise, let generator end gracefully
            Logger.base.info(f'🔌 [SSE] Client disconnected: buyer={buyer_id}, event={event_id}')

        finally:
            if pubsub is not None:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            Logger.base.info(f'🔌 [SSE] Unsubscribed from Redis channel: {channel}')

    return EventSourceResponse(event_generator())
