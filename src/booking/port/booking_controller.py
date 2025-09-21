from fastapi import APIRouter, Depends, status

from src.booking.port.booking_schema import (
    BookingCreateRequest,
    BookingResponse,
    CancelReservationResponse,
    PaymentRequest,
    PaymentResponse,
)
from src.booking.use_case.create_booking_use_case import CreateBookingUseCase
from src.booking.use_case.get_booking_use_case import GetBookingUseCase
from src.booking.use_case.list_bookings_use_case import ListBookingsUseCase
from src.booking.use_case.mock_payment_use_case import MockPaymentUseCase
from src.event_ticketing.use_case.cancel_reservation_use_case import CancelReservationUseCase
from src.shared.auth.current_user_info import CurrentUserInfo
from src.shared.logging.loguru_io import Logger
from src.shared.service.role_auth_service import get_current_user_info, require_buyer_info


router = APIRouter()


@router.post('', status_code=status.HTTP_201_CREATED)
@Logger.io
async def create_booking(
    request: BookingCreateRequest,
    current_user: CurrentUserInfo = Depends(require_buyer_info),
    use_case: CreateBookingUseCase = Depends(CreateBookingUseCase.depends),
) -> BookingResponse:
    # Use authenticated buyer's ID and handle both legacy and new seat selection approaches
    booking = await use_case.create_booking(
        buyer_id=current_user.user_id,
        ticket_ids=request.ticket_ids,
        seat_selection_mode=request.seat_selection_mode,
        selected_seats=request.selected_seats,
        quantity=request.quantity,
    )

    if booking.id is None:
        raise ValueError('Booking ID should not be None after creation.')

    return BookingResponse(
        id=booking.id,
        buyer_id=booking.buyer_id,
        seller_id=booking.seller_id,
        total_price=booking.total_price,
        status=booking.status.value,
        created_at=booking.created_at,
        paid_at=booking.paid_at,
    )


@router.get('/{booking_id}')
@Logger.io
async def get_booking(
    booking_id: int,
    current_user: CurrentUserInfo = Depends(get_current_user_info),
    use_case: GetBookingUseCase = Depends(GetBookingUseCase.depends),
) -> BookingResponse:
    booking = await use_case.get_booking(booking_id)

    return BookingResponse(
        id=booking_id,
        buyer_id=booking.buyer_id,
        seller_id=booking.seller_id,
        total_price=booking.total_price,
        status=booking.status.value,
        created_at=booking.created_at,
        paid_at=booking.paid_at,
    )


@router.patch('/{booking_id}', status_code=status.HTTP_204_NO_CONTENT)
@Logger.io
async def cancel_booking(
    booking_id: int,
    current_user: CurrentUserInfo = Depends(require_buyer_info),
    use_case: CancelReservationUseCase = Depends(CancelReservationUseCase.depends),
):
    result = await use_case.cancel_reservation(
        booking_id=booking_id,
        buyer_id=current_user.user_id,
    )
    return CancelReservationResponse(**result)


@router.post('/{booking_id}/pay')
@Logger.io
async def pay_booking(
    booking_id: int,
    request: PaymentRequest,
    current_user: CurrentUserInfo = Depends(require_buyer_info),
    use_case: MockPaymentUseCase = Depends(MockPaymentUseCase.depends),
) -> PaymentResponse:
    result = await use_case.pay_booking(
        booking_id=booking_id, buyer_id=current_user.user_id, card_number=request.card_number
    )

    return PaymentResponse(
        booking_id=result['booking_id'],
        payment_id=result['payment_id'],
        status=result['status'],
        paid_at=result['paid_at'],
    )


@router.get('/my-bookings')
@Logger.io
async def list_my_bookings(
    booking_status: str,
    current_user: CurrentUserInfo = Depends(get_current_user_info),
    use_case: ListBookingsUseCase = Depends(ListBookingsUseCase.depends),
):
    if current_user.is_buyer():
        return await use_case.list_buyer_bookings(current_user.user_id, booking_status)
    elif current_user.is_seller():
        return await use_case.list_seller_bookings(current_user.user_id, booking_status)
    else:
        return []
