"""Order controller."""

from typing import Optional

from fastapi import APIRouter, Depends, status

from src.order.port.order_schema import (
    OrderCreateRequest,
    OrderResponse,
    PaymentRequest,
    PaymentResponse,
)
from src.order.use_case.create_order_use_case import CreateOrderUseCase
from src.order.use_case.get_order_use_case import GetOrderUseCase
from src.order.use_case.list_orders_use_case import ListOrdersUseCase
from src.order.use_case.mock_payment_use_case import MockPaymentUseCase
from src.shared.logging.loguru_io import Logger
from src.shared.service.role_auth_service import get_current_user, require_buyer
from src.user.domain.user_entity import UserRole
from src.user.domain.user_model import User


router = APIRouter()


@router.post('', status_code=status.HTTP_201_CREATED)
@Logger.io
async def create_order(
    request: OrderCreateRequest,
    current_user: User = Depends(require_buyer),
    use_case: CreateOrderUseCase = Depends(CreateOrderUseCase.depends),
) -> OrderResponse:
    # Use authenticated buyer's ID instead of request.buyer_id
    order = await use_case.create_order(buyer_id=current_user.id, product_id=request.product_id)

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


@router.get('/my-orders')
@Logger.io
async def list_my_orders(
    order_status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    use_case: ListOrdersUseCase = Depends(ListOrdersUseCase.depends),
):
    if current_user.role == UserRole.BUYER:
        return await use_case.list_buyer_orders(current_user.id, order_status)
    elif current_user.role == UserRole.SELLER:
        return await use_case.list_seller_orders(current_user.id, order_status)
    else:
        return []


@router.get('/{order_id}')
@Logger.io
async def get_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    use_case: GetOrderUseCase = Depends(GetOrderUseCase.depends),
) -> OrderResponse:
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


@router.post('/{order_id}/pay')
@Logger.io
async def pay_order(
    order_id: int,
    request: PaymentRequest,
    current_user: User = Depends(require_buyer),
    use_case: MockPaymentUseCase = Depends(MockPaymentUseCase.depends),
) -> PaymentResponse:
    result = await use_case.pay_order(
        order_id=order_id, buyer_id=current_user.id, card_number=request.card_number
    )

    return PaymentResponse(
        order_id=result['order_id'],
        payment_id=result['payment_id'],
        status=result['status'],
        paid_at=result['paid_at'],
    )


@router.delete('/{order_id}', status_code=status.HTTP_204_NO_CONTENT)
@Logger.io
async def cancel_order(
    order_id: int,
    current_user: User = Depends(require_buyer),
    use_case: MockPaymentUseCase = Depends(MockPaymentUseCase.depends),
):
    await use_case.cancel_order(order_id=order_id, buyer_id=current_user.id)

    return None


@Logger.io
async def list_seller_orders(
    seller_id: int,
    order_status: Optional[str] = None,
    use_case: ListOrdersUseCase = Depends(ListOrdersUseCase.depends),
):
    return await use_case.list_seller_orders(seller_id, order_status)
