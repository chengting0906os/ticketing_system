"""Order controller."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.order.use_case.create_order_use_case import CreateOrderUseCase
from src.shared.exceptions import DomainException


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


router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_order(
    request: OrderCreateRequest,
    use_case: CreateOrderUseCase = Depends(CreateOrderUseCase.depends)
) -> OrderResponse:
    try:
        order = await use_case.create_order(
            buyer_id=request.buyer_id,
            product_id=request.product_id
        )
        
        if order.id is None:
            raise ValueError("Order ID should not be None after creation.")
        
        return OrderResponse(
            id=order.id,
            buyer_id=order.buyer_id,
            seller_id=order.seller_id,
            product_id=order.product_id,
            price=order.price,
            status=order.status.value,
            created_at=order.created_at,
            paid_at=order.paid_at
        )
    except DomainException as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
