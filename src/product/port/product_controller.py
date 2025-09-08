"""Product controller."""

from typing import List, Optional

from fastapi import APIRouter, Depends, status

from src.product.port.product_schema import (
    ProductCreateRequest,
    ProductResponse,
    ProductUpdateRequest,
)
from src.product.use_case.product_use_case import (
    CreateProductUseCase,
    DeleteProductUseCase,
    GetProductUseCase,
    ListProductsUseCase,
    UpdateProductUseCase,
)
from src.shared.exception.exceptions import NotFoundError
from src.shared.logging.loguru_io import Logger
from src.shared.service.role_auth_service import require_seller
from src.user.domain.user_model import User


router = APIRouter()


@router.post('', status_code=status.HTTP_201_CREATED)
@Logger.io
async def create_product(
    request: ProductCreateRequest,
    current_user: User = Depends(require_seller),
    use_case: CreateProductUseCase = Depends(CreateProductUseCase.depends),
) -> ProductResponse:
    product = await use_case.create(
        name=request.name,
        description=request.description,
        price=request.price,
        seller_id=current_user.id,  # Use current user's ID
        is_active=request.is_active,
    )

    if product.id is None:
        raise ValueError('Product ID should not be None after creation.')

    return ProductResponse(
        id=product.id,
        name=product.name,
        description=product.description,
        price=product.price,
        seller_id=product.seller_id,
        is_active=product.is_active,
        status=product.status.value,  # Convert enum to string
    )


@router.patch('/{product_id}', status_code=status.HTTP_200_OK)
async def update_product(
    product_id: int,
    request: ProductUpdateRequest,
    current_user: User = Depends(require_seller),
    use_case: UpdateProductUseCase = Depends(UpdateProductUseCase.depends),
) -> ProductResponse:
    product = await use_case.update(
        product_id=product_id,
        name=request.name,
        description=request.description,
        price=request.price,
        is_active=request.is_active,
    )

    if not product:
        raise NotFoundError(f'Product with id {product_id} not found')

    return ProductResponse(
        id=product_id,
        name=product.name,
        description=product.description,
        price=product.price,
        seller_id=product.seller_id,
        is_active=product.is_active,
        status=product.status.value,
    )


@router.delete('/{product_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: int,
    current_user: User = Depends(require_seller),
    use_case: DeleteProductUseCase = Depends(DeleteProductUseCase.depends),
):
    await use_case.delete(product_id)
    return None


@router.get('/{product_id}', status_code=status.HTTP_200_OK)
async def get_product(
    product_id: int, use_case: GetProductUseCase = Depends(GetProductUseCase.depends)
) -> ProductResponse:
    product = await use_case.get_by_id(product_id)

    if not product:
        raise NotFoundError(f'Product with id {product_id} not found')

    return ProductResponse(
        id=product_id,
        name=product.name,
        description=product.description,
        price=product.price,
        seller_id=product.seller_id,
        is_active=product.is_active,
        status=product.status.value,
    )


@router.get('', status_code=status.HTTP_200_OK)
async def list_products(
    seller_id: Optional[int] = None,
    use_case: ListProductsUseCase = Depends(ListProductsUseCase.depends),
) -> List[ProductResponse]:
    if seller_id is not None:
        products = await use_case.get_by_seller(seller_id)
    else:
        products = await use_case.list_available()

    result = []
    for product in products:
        if product.id is not None:
            result.append(
                ProductResponse(
                    id=product.id,
                    name=product.name,
                    description=product.description,
                    price=product.price,
                    seller_id=product.seller_id,
                    is_active=product.is_active,
                    status=product.status.value,
                )
            )
    return result
