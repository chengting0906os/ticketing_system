from typing import List

from fastapi import APIRouter, Depends, status

from src.platform.logging.loguru_io import Logger
from src.service.ticketing.app.command.create_booking_use_case import CreateBookingUseCase
from src.service.ticketing.app.command.mock_payment_and_update_booking_status_to_completed_and_ticket_to_paid_use_case import (
    MockPaymentAndUpdateBookingStatusToCompletedAndTicketToPaidUseCase,
)
from src.service.ticketing.app.command.update_booking_status_to_cancelled_use_case import (
    CancelBookingUseCase,
)
from src.service.ticketing.app.query.get_booking_use_case import GetBookingUseCase
from src.service.ticketing.app.query.list_bookings_use_case import ListBookingsUseCase
from src.service.ticketing.app.service.role_auth_service import (
    RoleAuthStrategy,
    get_current_user,
    require_buyer,
)
from src.service.ticketing.domain.entity.user_entity import UserEntity
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
async def list_my_bookings(
    booking_status: str = '',
    current_user: UserEntity = Depends(get_current_user),
    use_case: ListBookingsUseCase = Depends(ListBookingsUseCase.depends),
):
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
    booking_id: int,
    current_user: UserEntity = Depends(get_current_user),
    use_case: GetBookingUseCase = Depends(GetBookingUseCase.depends),
) -> BookingDetailResponse:
    booking_details = await use_case.get_booking_with_details(booking_id)
    return BookingDetailResponse(**booking_details)


@router.patch('/{booking_id}', status_code=status.HTTP_200_OK)
@Logger.io
async def cancel_booking(
    booking_id: int,
    current_user: UserEntity = Depends(require_buyer),
    use_case: CancelBookingUseCase = Depends(CancelBookingUseCase.depends),
):
    result = await use_case.cancel_booking(
        booking_id=booking_id,
        buyer_id=current_user.id or 0,
    )
    return CancelReservationResponse(**result)


@router.post('/{booking_id}/pay')
@Logger.io
async def pay_booking(
    booking_id: int,
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
