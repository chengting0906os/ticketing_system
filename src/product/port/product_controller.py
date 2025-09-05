"""Product controller."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.product.domain.errors import ProductDomainError
from src.product.use_case.product_use_case import CreateProductUseCase, UpdateProductUseCase


class ProductCreateRequest(BaseModel):
    name: str
    description: str
    price: int
    seller_id: int
    is_active: bool = True  # Default to active


class ProductResponse(BaseModel):
    id: int
    name: str
    description: str
    price: int
    seller_id: int
    is_active: bool
    status: str


class ProductUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[int] = None
    is_active: Optional[bool] = None


router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_product(
    request: ProductCreateRequest,
    use_case: CreateProductUseCase = Depends(CreateProductUseCase.depends)
) -> ProductResponse:
    try:
        product = await use_case.create(
            name=request.name,
            description=request.description,
            price=int(request.price),  # Ensure it's int
            seller_id=request.seller_id,
            is_active=request.is_active
        )

        if product.id is None:
            raise ValueError("Product ID should not be None after creation.")
        
        return ProductResponse(
            id=product.id,
            name=product.name,
            description=product.description,
            price=product.price,
            seller_id=product.seller_id,
            is_active=product.is_active,
            status=product.status.value  # Convert enum to string
        )
    except ProductDomainError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.patch("/{product_id}", status_code=status.HTTP_200_OK)
async def update_product(
    product_id: int,
    request: ProductUpdateRequest,
    use_case: UpdateProductUseCase = Depends(UpdateProductUseCase.depends)
) -> ProductResponse:
    try:
        product = await use_case.update(
            product_id=product_id,
            name=request.name,
            description=request.description,
            price=request.price,
            is_active=request.is_active
        )
        
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with id {product_id} not found"
            )
        
        if product.id is None:
            raise ValueError("Product ID should not be None after update.")
        
        return ProductResponse(
            id=product.id,
            name=product.name,
            description=product.description,
            price=product.price,
            seller_id=product.seller_id,
            is_active=product.is_active,
            status=product.status.value
        )
    except ProductDomainError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
