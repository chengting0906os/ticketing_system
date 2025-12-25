from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel

from src.platform.types import UtilsUUID7


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
    model_config = {
        'json_schema_extra': {
            'example': {
                'id': '01936d8f-5e73-7c4e-a9c5-123456789abc',  # UUID7
                'buyer_id': 2,
                'event_id': 1,
                'total_price': 2000,
                'status': 'pending_payment',
                'created_at': '2025-01-10T10:30:00',
                'paid_at': None,
            }
        },
    }

    id: UtilsUUID7  # UUID7
    buyer_id: int
    event_id: int
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
    model_config = {
        'arbitrary_types_allowed': True,
        'json_schema_extra': {
            'example': {
                'booking_id': '01936d8f-5e73-7c4e-a9c5-123456789abc',  # UUID7
                'payment_id': 'PAY-123456789',
                'status': 'success',
                'paid_at': '2025-01-10T10:35:00',
            }
        },
    }

    booking_id: UtilsUUID7  # UUID7
    payment_id: str
    status: str
    paid_at: Optional[str]


class CancelReservationResponse(BaseModel):
    status: str
    cancelled_tickets: int

    class Config:
        json_schema_extra = {'example': {'status': 'cancelled', 'cancelled_tickets': 2}}


class BookingWithDetailsResponse(BaseModel):
    """Booking response with event and user details"""

    id: UtilsUUID7  # UUID7
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

    class Config:
        json_schema_extra = {
            'example': {
                'id': '01936d8f-5e73-7c4e-a9c5-123456789abc',
                'buyer_id': 2,
                'event_id': 1,
                'total_price': 4000,
                'status': 'pending_payment',
                'created_at': '2025-01-10T10:30:00',
                'paid_at': None,
                'event_name': 'Concert Event',
                'buyer_name': 'John Doe',
                'seller_name': 'Jane Seller',
                'venue_name': 'Taipei Arena',
                'section': 'A',
                'subsection': 1,
                'quantity': 2,
                'seat_selection_mode': 'best_available',
                'seat_positions': ['1-1', '1-2'],
            }
        }


class TicketDetail(BaseModel):
    """Ticket detail in booking"""

    id: int
    section: str
    subsection: int
    row: int
    seat: int
    price: int
    status: str

    class Config:
        json_schema_extra = {
            'example': {
                'id': 1,
                'section': 'A',
                'subsection': 1,
                'row': 1,
                'seat': 1,
                'price': 2000,
                'status': 'reserved',
            }
        }


class BookingDetailResponse(BaseModel):
    """Detailed booking response with all information and tickets"""

    id: UtilsUUID7  # UUID7
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
    tickets: List[TicketDetail]

    class Config:
        json_schema_extra = {
            'example': {
                'id': '01936d8f-5e73-7c4e-a9c5-123456789abc',
                'buyer_id': 2,
                'event_id': 1,
                'total_price': 4000,
                'status': 'pending_payment',
                'created_at': '2025-01-10T10:30:00',
                'paid_at': None,
                'event_name': 'Concert Event',
                'buyer_name': 'John Doe',
                'seller_name': 'Jane Seller',
                'venue_name': 'Taipei Arena',
                'section': 'A',
                'subsection': 1,
                'quantity': 2,
                'seat_selection_mode': 'best_available',
                'seat_positions': ['1-1', '1-2'],
                'tickets': [
                    {
                        'id': 1,
                        'section': 'A',
                        'subsection': 1,
                        'row': 1,
                        'seat': 1,
                        'price': 2000,
                        'status': 'reserved',
                    },
                    {
                        'id': 2,
                        'section': 'A',
                        'subsection': 1,
                        'row': 1,
                        'seat': 2,
                        'price': 2000,
                        'status': 'reserved',
                    },
                ],
            }
        }
