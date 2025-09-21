from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, field_validator, model_validator


class BookingCreateRequest(BaseModel):
    event_id: int
    seat_selection_mode: Literal[
        'manual', 'best_available'
    ]  # Must be either 'best_available' or 'manual'
    selected_seats: List[
        dict
    ] = []  # For manual selection like [{1101: 'A-1-1-1'}, {1102: 'A-1-1-2'}]
    numbers_of_seats: Optional[int] = None  # For best available selection

    @field_validator('seat_selection_mode')
    @classmethod
    def validate_seat_selection_mode(cls, v):
        if v not in ['manual', 'best_available']:
            raise ValueError('seat_selection_mode must be either "manual" or "best_available"')
        return v

    @field_validator('numbers_of_seats')
    @classmethod
    def validate_numbers_of_seats(cls, v):
        if v is not None and (v < 1 or v > 4):
            raise ValueError('numbers_of_seats must be between 1 and 4')
        return v

    @field_validator('selected_seats')
    @classmethod
    def validate_selected_seats(cls, v):
        if v is not None:
            if len(v) > 4:
                raise ValueError('Maximum 4 tickets per booking')
            normalized_seats = []
            for seat_dict in v:
                if not isinstance(seat_dict, dict):
                    raise ValueError(
                        'Each selected seat must be a dict with format {ticket_id: seat_location}'
                    )
                if len(seat_dict) != 1:
                    raise ValueError(
                        'Each seat dict must contain exactly one ticket_id: seat_location pair'
                    )

                # Get ticket_id and seat_location
                ticket_id, seat_location = next(iter(seat_dict.items()))

                # Validate ticket_id (convert from string if needed, as JSON keys are always strings)
                try:
                    ticket_id_int = int(ticket_id) if isinstance(ticket_id, str) else ticket_id
                    if not isinstance(ticket_id_int, int):
                        raise ValueError('ticket_id must be an integer')
                except ValueError:
                    raise ValueError('ticket_id must be an integer')

                # Validate seat_location format
                if not isinstance(seat_location, str):
                    raise ValueError('seat_location must be a string')

                parts = seat_location.split('-')
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

                # Add the normalized dict with integer ticket_id
                normalized_seats.append({ticket_id_int: seat_location})

            # Return the normalized list with integer ticket_ids
            return normalized_seats
        return v

    @model_validator(mode='before')
    @classmethod
    def validate_booking_request(cls, values):
        """Validate the entire booking request for logical consistency"""
        seat_selection_mode = values.get('seat_selection_mode')
        selected_seats = values.get('selected_seats', [])
        numbers_of_seats = values.get('numbers_of_seats')

        # Validate based on seat_selection_mode
        if seat_selection_mode == 'manual':
            if not selected_seats or len(selected_seats) == 0:
                raise ValueError('selected_seats is required for manual selection')
            if numbers_of_seats is not None:
                raise ValueError('Cannot specify numbers_of_seats for manual selection')
        elif seat_selection_mode == 'best_available':
            if selected_seats and len(selected_seats) > 0:
                raise ValueError('selected_seats must be empty for best_available selection')
            if numbers_of_seats is None:
                raise ValueError('numbers_of_seats is required for best_available selection')

        return values

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'event_id': 1,
                    'seat_selection_mode': 'best_available',
                    'selected_seats': [],
                    'numbers_of_seats': 2,
                },
                {'event_id': 1, 'seat_selection_mode': 'best_available', 'numbers_of_seats': 3},
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


class CancelReservationResponse(BaseModel):
    status: str
    cancelled_tickets: int
