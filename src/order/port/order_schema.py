from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class OrderCreateRequest(BaseModel):
    buyer_id: int
    product_id: int


class OrderResponse(BaseModel):
    id: int
    buyer_id: int
    seller_id: int
    product_id: int
    price: int
    status: str
    created_at: datetime
    paid_at: Optional[datetime]


class PaymentRequest(BaseModel):
    card_number: str
    buyer_id: int


class PaymentResponse(BaseModel):
    order_id: int
    payment_id: str
    status: str
    paid_at: Optional[str]


class CancelRequest(BaseModel):
    buyer_id: int
