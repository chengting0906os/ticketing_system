from typing import Dict, Optional

from pydantic import BaseModel


class EventCreateRequest(BaseModel):
    name: str
    description: str
    price: int
    venue_name: str
    seating_config: Dict
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


class EventResponse(BaseModel):
    id: int
    name: str
    description: str
    price: int
    seller_id: int
    venue_name: str
    seating_config: Dict
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


class EventUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[int] = None
    venue_name: Optional[str] = None
    seating_config: Optional[Dict] = None
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
