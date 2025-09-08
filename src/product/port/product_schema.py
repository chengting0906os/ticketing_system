from typing import Optional

from pydantic import BaseModel


class ProductCreateRequest(BaseModel):
    name: str
    description: str
    price: int
    is_active: bool = True

    class Config:
        json_schema_extra = {
            'example': {
                'name': 'iPhone 15 Pro',
                'description': 'Latest Apple smartphone with A17 Pro chip',
                'price': 39900,
                'is_active': True,
            }
        }


class ProductResponse(BaseModel):
    id: int
    name: str
    description: str
    price: int
    seller_id: int
    is_active: bool
    status: str

    class Config:
        json_schema_extra = {
            'example': {
                'id': 1,
                'name': 'iPhone 15 Pro',
                'description': 'Latest Apple smartphone with A17 Pro chip',
                'price': 39900,
                'seller_id': 1,
                'is_active': True,
                'status': 'available',
            }
        }


class ProductUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[int] = None
    is_active: Optional[bool] = None

    class Config:
        json_schema_extra = {
            'example': {
                'name': 'iPhone 15 Pro Max',
                'description': 'Updated description with new features',
                'price': 42900,
                'is_active': True,
            }
        }
