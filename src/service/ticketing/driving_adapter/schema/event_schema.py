from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EventCreateWithTicketConfigRequest(BaseModel):
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
                            'price': 2000,
                            'subsections': [
                                {'number': 1, 'rows': 25, 'seats_per_row': 20},
                                {'number': 2, 'rows': 25, 'seats_per_row': 20},
                            ],
                        },
                        {
                            'name': 'B',
                            'price': 1500,
                            'subsections': [
                                {'number': 1, 'rows': 25, 'seats_per_row': 20},
                                {'number': 2, 'rows': 25, 'seats_per_row': 20},
                            ],
                        },
                        {
                            'name': 'C',
                            'price': 1000,
                            'subsections': [
                                {'number': 1, 'rows': 25, 'seats_per_row': 20},
                                {'number': 2, 'rows': 25, 'seats_per_row': 20},
                            ],
                        },
                    ]
                },
                'is_active': True,
            }
        }


class TicketResponse(BaseModel):
    """票券回應 Schema"""

    model_config = ConfigDict(
        json_schema_extra={
            'example': {
                'id': '01234567-89ab-7def-0123-456789abcdef',
                'event_id': '00000000-0000-0000-0000-000000000001',
                'section': 'A',
                'subsection': 1,
                'row': 1,
                'seat': 1,
                'price': 2000,
                'status': 'sold',
                'seat_identifier': 'A-1-1-1',
                'buyer_id': '01234567-89ab-7def-0123-456789abcdef',
            }
        }
    )

    id: UUID
    event_id: UUID
    section: str
    subsection: int
    row: int
    seat: int
    price: int
    status: str
    seat_identifier: str
    buyer_id: Optional[UUID] = None


class EventResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            'example': {
                'id': '00000000-0000-0000-0000-000000000001',
                'name': 'iPhone 15 Pro',
                'description': 'Latest Apple smartphone with A17 Pro chip',
                'seller_id': '01234567-89ab-7def-0123-456789abcdef',
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
    )

    id: UUID
    name: str
    description: str
    seller_id: UUID
    venue_name: str
    seating_config: Dict
    is_active: bool
    status: str
    tickets: List[TicketResponse] = []
