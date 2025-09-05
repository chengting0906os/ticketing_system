"""Product controller."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.product.domain.errors import ProductDomainError
from src.product.use_case.use_case import CreateProductUseCase


class ProductCreateRequest(BaseModel):
    name: str
    description: str
    price: int
    seller_id: int


class ProductResponse(BaseModel):
    id: int
    name: str
    description: str
    price: int
    seller_id: int


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
            seller_id=request.seller_id
        )
        
        return ProductResponse(
            id=product.id,
            name=product.name,
            description=product.description,
            price=product.price,
            seller_id=product.seller_id
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
