from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, field_validator, model_validator


class BookingCreateRequest(BaseModel):
    # Legacy approach - providing ticket IDs directly
    ticket_ids: Optional[List[int]] = None

    # New seat selection approach
    seat_selection_mode: Optional[str] = None
    selected_seats: Optional[List[str]] = None  # For manual selection like ["A-1-1", "A-1-2"]
    quantity: Optional[int] = None  # For best available selection

    @field_validator('seat_selection_mode')
    @classmethod
    def validate_seat_selection_mode(cls, v):
        if v is not None and v not in ['manual', 'best_available']:
            raise ValueError('seat_selection_mode must be either "manual" or "best_available"')
        return v

    @field_validator('quantity')
    @classmethod
    def validate_quantity(cls, v):
        if v is not None and (v < 1 or v > 4):
            raise ValueError('Quantity must be between 1 and 4')
        return v

    @field_validator('selected_seats')
    @classmethod
    def validate_selected_seats(cls, v):
        if v is not None:
            if len(v) > 4:
                raise ValueError('Maximum 4 tickets per booking')
            for seat in v:
                parts = seat.split('-')
                if len(parts) != 4:
                    raise ValueError(
                        'Invalid seat format. Expected: section-subsection-row-seat (e.g., A-1-1-1)'
                    )
                try:
                    # Validate section (string), subsection (int), row (int), seat (int)
                    subsection = int(parts[1])
                    row = int(parts[2])
                    seat_num = int(parts[3])
                    if subsection <= 0 or row <= 0 or seat_num <= 0:
                        raise ValueError('Subsection, row and seat numbers must be positive')
                except ValueError:
                    raise ValueError(
                        'Invalid seat format. Expected: section-subsection-row-seat (e.g., A-1-1-1)'
                    )
        return v

    @model_validator(mode='before')
    @classmethod
    def validate_booking_request(cls, values):
        """Validate the entire booking request for logical consistency"""
        ticket_ids = values.get('ticket_ids')
        seat_selection_mode = values.get('seat_selection_mode')
        selected_seats = values.get('selected_seats')
        quantity = values.get('quantity')

        # Count how many booking approaches are being used
        approaches_used = 0
        if ticket_ids is not None:
            approaches_used += 1
        if seat_selection_mode is not None:
            approaches_used += 1

        # Only one approach should be used
        if approaches_used == 0:
            raise ValueError('Must provide either ticket_ids or seat_selection_mode')
        elif approaches_used > 1:
            raise ValueError('Cannot mix ticket_ids with seat selection mode')

        # If using seat selection mode, validate the parameters
        if seat_selection_mode == 'manual':
            if selected_seats is None or len(selected_seats) == 0:
                raise ValueError('selected_seats is required for manual selection')
            if quantity is not None:
                raise ValueError('Cannot specify both selected_seats and quantity')
        elif seat_selection_mode == 'best_available':
            if quantity is None:
                raise ValueError('quantity is required for best_available selection')
            if selected_seats is not None:
                raise ValueError('Cannot specify selected_seats for best_available selection')

        return values

    class Config:
        json_schema_extra = {
            'examples': [
                {'ticket_ids': [1001, 1002]},
                {'seat_selection_mode': 'manual', 'selected_seats': ['A-1-1-1', 'A-1-1-2']},
                {'seat_selection_mode': 'best_available', 'quantity': 3},
            ]
        }


class BookingResponse(BaseModel):
    id: int
    buyer_id: int
    seller_id: int
    total_price: int
    status: str
    created_at: datetime
    paid_at: Optional[datetime]

    class Config:
        json_schema_extra = {
            'example': {
                'id': 1,
                'buyer_id': 2,
                'seller_id': 1,
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
