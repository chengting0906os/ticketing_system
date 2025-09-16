from typing import Dict, Optional

from pydantic import BaseModel


class EventCreateRequest(BaseModel):
    name: str
    description: str
    venue_name: str
    seating_config: Dict
    is_active: bool = True

    class Config:
        json_schema_extra = {
            'example': {
                'name': 'Concert Event',
                'description': 'Amazing live music performance',
                'venue_name': 'Taipei Arena',
                'seating_config': {
                    'sections': [
                        {
                            'name': 'A',
                            'price': 1000,
                            'subsections': [{'number': 1, 'rows': 25, 'seats_per_row': 20}],
                        }
                    ]
                },
                'is_active': True,
            }
        }


class EventResponse(BaseModel):
    id: int
    name: str
    description: str
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
                'seller_id': 1,
                'venue_name': 'Taipei Arena',
                'seating_config': {
                    'sections': [
                        {
                            'name': 'A',
                            'subsections': [{'number': 1, 'rows': 25, 'seats_per_row': 20}],
                        }
                    ]
                },
                'is_active': True,
                'status': 'available',
            }
        }


class EventUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    venue_name: Optional[str] = None
    seating_config: Optional[Dict] = None
    is_active: Optional[bool] = None

    class Config:
        json_schema_extra = {
            'example': {
                'name': 'iPhone 15 Pro Max',
                'description': 'Updated description with new features',
                'venue_name': 'Taipei Dome',
                'is_active': True,
            }
        }
