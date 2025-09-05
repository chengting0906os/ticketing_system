from typing import Optional

from pydantic import BaseModel


class ProductCreateRequest(BaseModel):
    name: str
    description: str
    price: int
    seller_id: int
    is_active: bool = True  


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
