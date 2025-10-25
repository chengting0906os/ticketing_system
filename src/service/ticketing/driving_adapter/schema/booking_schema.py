from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BookingCreateRequest(BaseModel):
    event_id: UUID
    section: str
    subsection: int
    seat_selection_mode: Literal['manual', 'best_available']
    seat_positions: List[str] = []  # For manual: [1-1,1-2], For best_available: []
    quantity: int  # For best_available selection

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'event_id': '00000000-0000-0000-0000-000000000001',
                    'section': 'A',
                    'subsection': 1,
                    'seat_positions': [],
                    'seat_selection_mode': 'best_available',
                    'quantity': 2,
                },
                {
                    'event_id': '00000000-0000-0000-0000-000000000001',
                    'seat_selection_mode': 'best_available',
                    'quantity': 3,
                },
            ]
        }


class BookingResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            'example': {
                'id': '01234567-89ab-7def-0123-456789abcdef',
                'buyer_id': '01234567-89ab-7def-0123-456789abcdef',
                'event_id': '00000000-0000-0000-0000-000000000001',
                'total_price': 2000,
                'status': 'pending_payment',
                'created_at': '2025-01-10T10:30:00',
                'paid_at': None,
            }
        }
    )

    id: UUID
    buyer_id: UUID
    event_id: UUID
    total_price: int
    status: str
    created_at: datetime
    paid_at: Optional[datetime] = None


class BookingStatusUpdateRequest(BaseModel):
    status: str

    class Config:
        json_schema_extra = {'example': {'status': 'pending_payment'}}


class PaymentRequest(BaseModel):
    card_number: str

    class Config:
        json_schema_extra = {'example': {'card_number': '4111111111111111'}}


class PaymentResponse(BaseModel):
    booking_id: UUID
    payment_id: str
    status: str
    paid_at: Optional[str]

    class Config:
        json_schema_extra = {
            'example': {
                'booking_id': '01234567-89ab-cdef-0123-456789abcdef',
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

    id: UUID
    buyer_id: UUID
    event_id: UUID
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


class TicketDetail(BaseModel):
    """Ticket detail in booking"""

    id: UUID
    section: str
    subsection: int
    row: int
    seat: int
    price: int
    status: str


class BookingDetailResponse(BaseModel):
    """Detailed booking response with all information and tickets"""

    id: UUID
    buyer_id: UUID
    event_id: UUID
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
    tickets: List[TicketDetail]
