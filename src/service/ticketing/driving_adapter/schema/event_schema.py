from typing import Dict, List, Optional

from pydantic import BaseModel


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
                                {'number': 1, 'rows': 25, 'cols': 20},
                                {'number': 2, 'rows': 25, 'cols': 20},
                            ],
                        },
                        {
                            'name': 'B',
                            'price': 1500,
                            'subsections': [
                                {'number': 1, 'rows': 25, 'cols': 20},
                                {'number': 2, 'rows': 25, 'cols': 20},
                            ],
                        },
                        {
                            'name': 'C',
                            'price': 1000,
                            'subsections': [
                                {'number': 1, 'rows': 25, 'cols': 20},
                                {'number': 2, 'rows': 25, 'cols': 20},
                            ],
                        },
                    ]
                },
                'is_active': True,
            }
        }


class TicketResponse(BaseModel):
    id: int
    event_id: int
    section: str
    subsection: int
    row: int
    seat: int
    price: int
    status: str
    seat_identifier: str
    buyer_id: Optional[int] = None

    class Config:
        json_schema_extra = {
            'example': {
                'id': 1,
                'event_id': 1,
                'section': 'A',
                'subsection': 1,
                'row': 1,
                'seat': 1,
                'price': 2000,
                'status': 'sold',
                'seat_identifier': 'A-1-1-1',
                'buyer_id': 123,
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
    tickets: List[TicketResponse] = []

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
                            'subsections': [{'number': 1, 'rows': 25, 'cols': 20}],
                        }
                    ]
                },
                'is_active': True,
                'status': 'available',
            }
        }
