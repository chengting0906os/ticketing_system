from typing import Dict, List

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
                            'subsections': [{'number': 1, 'rows': 25, 'cols': 20}],
                        }
                    ]
                },
                'is_active': True,
                'status': 'available',
            }
        }


class SeatResponse(BaseModel):
    """Seat Response Schema (queried from Kvrocks)."""

    event_id: int
    section: str
    subsection: int
    seat_positions: List[str]  # format: ["{row}-{seat}", ...], e.g., ["1-1", "1-2"]
    price: int
    status: str

    class Config:
        json_schema_extra = {
            'example': {
                'event_id': 1,
                'section': 'A',
                'subsection': 1,
                'seat_positions': ['1-1', '1-2', '1-3'],
                'price': 2000,
                'status': 'available',
            }
        }


class SectionStatsResponse(BaseModel):
    """Section Statistics Response."""

    event_id: int
    section: str
    subsection: int
    total: int
    available: int
    reserved: int
    sold: int
    tickets: List[SeatResponse] = []
    total_count: int = 0

    class Config:
        json_schema_extra = {
            'example': {
                'event_id': 1,
                'section': 'A',
                'subsection': 1,
                'total': 3000,
                'available': 480,
                'reserved': 15,
                'sold': 5,
                'tickets': ['1-1', '1-2'],
                'total_count': 500,
            }
        }


# ============================ SSE Schemas ============================


class EventStateSseResponse(BaseModel):
    """SSE response for event state updates."""

    event_type: str
    event_id: int
    name: str
    description: str
    seller_id: int
    is_active: bool
    status: str
    venue_name: str
    seating_config: Dict
    sections: Dict
    total_sections: int
