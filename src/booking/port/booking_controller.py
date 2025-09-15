from fastapi import APIRouter, Depends, status

from src.booking.port.booking_schema import (
    BookingCreateRequest,
    BookingResponse,
    PaymentRequest,
    PaymentResponse,
)
from src.booking.use_case.create_booking_use_case import CreateBookingUseCase
from src.booking.use_case.get_booking_use_case import GetBookingUseCase
from src.booking.use_case.list_bookings_use_case import ListBookingsUseCase
from src.booking.use_case.mock_payment_use_case import MockPaymentUseCase
from src.shared.logging.loguru_io import Logger
from src.shared.service.role_auth_service import get_current_user, require_buyer
from src.ticket.port.ticket_schema import CancelReservationResponse
from src.ticket.use_case.cancel_reservation_use_case import CancelReservationUseCase
from src.user.domain.user_entity import UserRole
from src.user.domain.user_model import User


router = APIRouter()


@router.post('', status_code=status.HTTP_201_CREATED)
@Logger.io
async def create_booking(
    request: BookingCreateRequest,
    current_user: User = Depends(require_buyer),
    use_case: CreateBookingUseCase = Depends(CreateBookingUseCase.depends),
) -> BookingResponse:
    # Use authenticated buyer's ID and handle both legacy and new seat selection approaches
    booking = await use_case.create_booking(
        buyer_id=current_user.id,
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


@router.get('/my-bookings')
@Logger.io
async def list_my_bookings(
    booking_status: str,
    current_user: User = Depends(get_current_user),
    use_case: ListBookingsUseCase = Depends(ListBookingsUseCase.depends),
):
    if current_user.role == UserRole.BUYER:
        return await use_case.list_buyer_bookings(current_user.id, booking_status)
    elif current_user.role == UserRole.SELLER:
        return await use_case.list_seller_bookings(current_user.id, booking_status)
    else:
        return []


@router.get('/{booking_id}')
@Logger.io
async def get_booking(
    booking_id: int,
    current_user: User = Depends(get_current_user),
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


@router.post('/{booking_id}/pay')
@Logger.io
async def pay_booking(
    booking_id: int,
    request: PaymentRequest,
    current_user: User = Depends(require_buyer),
    use_case: MockPaymentUseCase = Depends(MockPaymentUseCase.depends),
) -> PaymentResponse:
    result = await use_case.pay_booking(
        booking_id=booking_id, buyer_id=current_user.id, card_number=request.card_number
    )

    return PaymentResponse(
        booking_id=result['booking_id'],
        payment_id=result['payment_id'],
        status=result['status'],
        paid_at=result['paid_at'],
    )


@router.delete('/{booking_id}', status_code=status.HTTP_204_NO_CONTENT)
@Logger.io
async def cancel_booking(
    booking_id: int,
    current_user: User = Depends(require_buyer),
    use_case: CancelReservationUseCase = Depends(CancelReservationUseCase.depends),
):
    await use_case.cancel_reservation(
        booking_id=booking_id,
        buyer_id=current_user.id,
    )
    # Return 204 No Content for successful deletion


@router.patch('/{booking_id}/cancel-reservation', status_code=status.HTTP_200_OK)
@Logger.io
async def cancel_reservation(
    booking_id: int,
    current_user: User = Depends(require_buyer),
    use_case: CancelReservationUseCase = Depends(CancelReservationUseCase.depends),
) -> CancelReservationResponse:
    result = await use_case.cancel_reservation(
        booking_id=booking_id,
        buyer_id=current_user.id,
    )

    return CancelReservationResponse(**result)


@Logger.io
async def list_seller_bookings(
    seller_id: int,
    booking_status: str,
    use_case: ListBookingsUseCase = Depends(ListBookingsUseCase.depends),
):
    return await use_case.list_seller_bookings(seller_id, booking_status)
