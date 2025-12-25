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
                    'rows': 25,
                    'cols': 20,
                    'sections': [
                        {'name': 'A', 'price': 2000, 'subsections': 2},
                        {'name': 'B', 'price': 1500, 'subsections': 2},
                        {'name': 'C', 'price': 1000, 'subsections': 2},
                    ],
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
    stats: dict | None

    class Config:
        json_schema_extra = {
            'example': {
                'id': 1,
                'name': 'Concert Event',
                'description': 'Amazing live music performance',
                'seller_id': 1,
                'venue_name': 'Taipei Arena',
                'seating_config': {
                    'rows': 25,
                    'cols': 20,
                    'sections': [
                        {'name': 'A', 'price': 2000, 'subsections': 2},
                    ],
                },
                'is_active': True,
                'status': 'available',
                'stats': {'available': 1000, 'reserved': 0, 'sold': 0, 'total': 1000},
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


class SubsectionStatsResponse(BaseModel):
    """Subsection statistics for seat availability."""

    event_id: int
    section: str
    subsection: int
    price: int
    available: int
    reserved: int
    sold: int

    class Config:
        json_schema_extra = {
            'example': {
                'event_id': 1,
                'section': 'A',
                'subsection': 1,
                'price': 2000,
                'available': 48,
                'reserved': 2,
                'sold': 0,
            }
        }


class EventWithSubsectionStatsResponse(BaseModel):
    """Event response with subsection statistics."""

    id: int
    name: str
    description: str
    seller_id: int
    is_active: bool
    status: str
    venue_name: str
    seating_config: Dict
    stats: dict
    sections: List[SubsectionStatsResponse]

    class Config:
        json_schema_extra = {
            'example': {
                'id': 3,
                'name': 'Concert Event',
                'description': 'Amazing live music performance',
                'seller_id': 1,
                'is_active': True,
                'status': 'available',
                'venue_name': 'Taipei Arena',
                'seating_config': {
                    'cols': 20,
                    'rows': 25,
                    'sections': [
                        {'name': 'A', 'price': 2000, 'subsections': 2},
                        {'name': 'B', 'price': 1500, 'subsections': 2},
                    ],
                },
                'stats': {'sold': 0, 'total': 2000, 'reserved': 0, 'available': 2000},
                'sections': [
                    {
                        'event_id': 3,
                        'section': 'A',
                        'subsection': 1,
                        'price': 2000,
                        'available': 500,
                        'reserved': 0,
                        'sold': 0,
                    },
                    {
                        'event_id': 3,
                        'section': 'A',
                        'subsection': 2,
                        'price': 2000,
                        'available': 500,
                        'reserved': 0,
                        'sold': 0,
                    },
                ],
            }
        }


class TicketResponse(BaseModel):
    """Ticket response."""

    id: Optional[int] = None
    event_id: int
    section: str
    subsection: int
    row: int
    seat: int
    price: int
    status: str

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
                'status': 'available',
            }
        }


class SubsectionSeatsResponse(BaseModel):
    """Subsection seats response with stats and tickets."""

    event_id: int
    section: str
    subsection: int
    price: int
    total: int
    available: int
    reserved: int
    sold: int
    tickets: List[TicketResponse]

    class Config:
        json_schema_extra = {
            'example': {
                'event_id': 1,
                'section': 'A',
                'subsection': 1,
                'price': 2000,
                'total': 50,
                'available': 48,
                'reserved': 2,
                'sold': 0,
                'tickets': [
                    {
                        'id': 1,
                        'event_id': 1,
                        'section': 'A',
                        'subsection': 1,
                        'row': 1,
                        'seat': 1,
                        'price': 2000,
                        'status': 'available',
                    },
                    {
                        'id': 2,
                        'event_id': 1,
                        'section': 'A',
                        'subsection': 1,
                        'row': 1,
                        'seat': 2,
                        'price': 2000,
                        'status': 'reserved',
                    },
                ],
            }
        }


# ============================ SSE Schemas ============================


class EventStateSseResponse(BaseModel):
    """SSE response for initial event state (full data)."""

    event_type: str
    event_id: int
    stats: dict
    name: str
    description: str
    seller_id: int
    is_active: bool
    status: str
    venue_name: str
    seating_config: Dict
    sections: List[SubsectionStatsResponse]

    class Config:
        json_schema_extra = {
            'example': {
                'event_type': 'initial_status',
                'event_id': 1,
                'stats': {'available': 1000, 'reserved': 0, 'sold': 0, 'total': 1000},
                'name': 'Concert Event',
                'description': 'Amazing live music performance',
                'seller_id': 1,
                'is_active': True,
                'status': 'available',
                'venue_name': 'Taipei Arena',
                'seating_config': {
                    'rows': 25,
                    'cols': 20,
                    'sections': [{'name': 'A', 'price': 2000, 'subsections': 2}],
                },
                'sections': [
                    {
                        'event_id': 1,
                        'section': 'A',
                        'subsection': 1,
                        'price': 2000,
                        'available': 500,
                        'reserved': 0,
                        'sold': 0,
                    }
                ],
            }
        }


class EventStateSseUpdateResponse(BaseModel):
    """SSE response for status updates (only changed fields)."""

    event_type: str
    event_id: int
    stats: dict
    subsection_stats: List[Dict]

    class Config:
        json_schema_extra = {
            'example': {
                'event_type': 'status_update',
                'event_id': 1,
                'stats': {'available': 998, 'reserved': 2, 'sold': 0, 'total': 1000},
                'subsection_stats': [
                    {
                        'event_id': 1,
                        'section': 'A',
                        'subsection': 1,
                        'price': 2000,
                        'available': 498,
                        'reserved': 2,
                        'sold': 0,
                    }
                ],
            }
        }
