from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel


class BookingCreateRequest(BaseModel):
    event_id: int
    section: str
    subsection: int
    seat_selection_mode: Literal['manual', 'best_available']
    seat_positions: List[str] = []  # For manual: [1-1,1-2], For best_available: []
    quantity: int  # For best_available selection

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'event_id': 1,
                    'section': 'A',
                    'subsection': 1,
                    'seat_positions': [],
                    'seat_selection_mode': 'best_available',
                    'quantity': 2,
                },
                {'event_id': 1, 'seat_selection_mode': 'best_available', 'quantity': 3},
            ]
        }


class BookingResponse(BaseModel):
    id: int
    buyer_id: int
    event_id: int
    total_price: int
    status: str
    created_at: datetime
    paid_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            'example': {
                'id': 1,
                'buyer_id': 2,
                'event_id': 1,
                'total_price': 2000,
                'status': 'pending_payment',
                'created_at': '2025-01-10T10:30:00',
                'paid_at': None,
            }
        }


class BookingStatusUpdateRequest(BaseModel):
    status: str

    class Config:
        json_schema_extra = {'example': {'status': 'pending_payment'}}


class PaymentRequest(BaseModel):
    card_number: str

    class Config:
        json_schema_extra = {'example': {'card_number': '4111111111111111'}}


class PaymentResponse(BaseModel):
    booking_id: int
    payment_id: str
    status: str
    paid_at: Optional[str]

    class Config:
        json_schema_extra = {
            'example': {
                'booking_id': 1,
                'payment_id': 'PAY-123456789',
                'status': 'success',
                'paid_at': '2025-01-10T10:35:00',
            }
        }


class CancelReservationResponse(BaseModel):
    status: str
    cancelled_tickets: int


class BookingWithDetailsResponse(BaseModel):
    """Booking response with event and user details"""

    id: int
    buyer_id: int
    event_id: int
    total_price: int
    status: str
    created_at: datetime
    paid_at: datetime | None = None
    event_name: str
    buyer_name: str
    seller_name: str
    venue_name: str
    section: str
    subsection: int
    quantity: int
    seat_selection_mode: str
    seat_positions: List[str]
