"""Order controller."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.order.use_case.create_order_use_case import CreateOrderUseCase
from src.order.use_case.get_order_use_case import GetOrderUseCase
from src.order.use_case.list_orders_use_case import ListOrdersUseCase
from src.order.use_case.mock_payment_use_case import MockPaymentUseCase
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


router = APIRouter()


@router.post('', status_code=status.HTTP_201_CREATED)
async def create_order(
    request: OrderCreateRequest, use_case: CreateOrderUseCase = Depends(CreateOrderUseCase.depends)
) -> OrderResponse:
    try:
        order = await use_case.create_order(
            buyer_id=request.buyer_id, product_id=request.product_id
        )

        if order.id is None:
            raise ValueError('Order ID should not be None after creation.')

        return OrderResponse(
            id=order.id,
            buyer_id=order.buyer_id,
            seller_id=order.seller_id,
            product_id=order.product_id,
            price=order.price,
            status=order.status.value,
            created_at=order.created_at,
            paid_at=order.paid_at,
        )
    except DomainException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get('/{order_id}')
async def get_order(
    order_id: int, use_case: GetOrderUseCase = Depends(GetOrderUseCase.depends)
) -> OrderResponse:
    try:
        order = await use_case.get_order(order_id)
        if order.id is None:
            raise ValueError('Order ID should not be None.')

        return OrderResponse(
            id=order.id,
            buyer_id=order.buyer_id,
            seller_id=order.seller_id,
            product_id=order.product_id,
            price=order.price,
            status=order.status.value,
            created_at=order.created_at,
            paid_at=order.paid_at,
        )
    except DomainException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post('/{order_id}/pay')
async def pay_order(
    order_id: int,
    request: PaymentRequest,
    use_case: MockPaymentUseCase = Depends(MockPaymentUseCase.depends),
) -> PaymentResponse:
    try:
        result = await use_case.pay_order(
            order_id=order_id, buyer_id=request.buyer_id, card_number=request.card_number
        )

        return PaymentResponse(
            order_id=result['order_id'],
            payment_id=result['payment_id'],
            status=result['status'],
            paid_at=result['paid_at'],
        )
    except DomainException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete('/{order_id}', status_code=status.HTTP_204_NO_CONTENT)
async def cancel_order(
    order_id: int, buyer_id: int, use_case: MockPaymentUseCase = Depends(MockPaymentUseCase.depends)
):
    try:
        await use_case.cancel_order(order_id=order_id, buyer_id=buyer_id)

        return None
    except DomainException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get('/buyer/{buyer_id}')
async def list_buyer_orders(
    buyer_id: int,
    order_status: Optional[str] = None,
    use_case: ListOrdersUseCase = Depends(ListOrdersUseCase.depends),
):
    try:
        return await use_case.list_buyer_orders(buyer_id, order_status)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get('/seller/{seller_id}')
async def list_seller_orders(
    seller_id: int,
    order_status: Optional[str] = None,
    use_case: ListOrdersUseCase = Depends(ListOrdersUseCase.depends),
):
    try:
        return await use_case.list_seller_orders(seller_id, order_status)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
