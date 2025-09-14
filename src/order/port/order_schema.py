from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class OrderCreateRequest(BaseModel):
    ticket_ids: List[int]

    class Config:
        json_schema_extra = {'example': {'ticket_ids': [1001, 1002]}}


class OrderResponse(BaseModel):
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


class OrderStatusUpdateRequest(BaseModel):
    status: str

    class Config:
        json_schema_extra = {'example': {'status': 'pending_payment'}}


class PaymentRequest(BaseModel):
    card_number: str

    class Config:
        json_schema_extra = {'example': {'card_number': '4111111111111111'}}


class PaymentResponse(BaseModel):
    order_id: int
    payment_id: str
    status: str
    paid_at: Optional[str]

    class Config:
        json_schema_extra = {
            'example': {
                'order_id': 1,
                'payment_id': 'PAY-123456789',
                'status': 'success',
                'paid_at': '2025-01-10T10:35:00',
            }
        }
