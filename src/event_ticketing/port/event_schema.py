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


class SubsectionAvailability(BaseModel):
    subsection: int
    total_tickets: int
    available_tickets: int
    reserved_tickets: int
    sold_tickets: int


class SectionAvailability(BaseModel):
    section: str
    total_tickets: int
    available_tickets: int
    reserved_tickets: int
    sold_tickets: int
    subsections: List[SubsectionAvailability]


class EventAvailabilityResponse(BaseModel):
    event_id: int
    total_tickets: int
    available_tickets: int
    reserved_tickets: int
    sold_tickets: int
    sections: List[SectionAvailability]

    class Config:
        json_schema_extra = {
            'example': {
                'event_id': 1,
                'total_tickets': 2500,
                'available_tickets': 2480,
                'reserved_tickets': 15,
                'sold_tickets': 5,
                'sections': [
                    {
                        'section': 'A',
                        'total_tickets': 500,
                        'available_tickets': 496,
                        'reserved_tickets': 3,
                        'sold_tickets': 1,
                        'subsections': [
                            {
                                'subsection': 1,
                                'total_tickets': 100,
                                'available_tickets': 99,
                                'reserved_tickets': 1,
                                'sold_tickets': 0,
                            }
                        ],
                    }
                ],
            }
        }


class SectionAvailabilityResponse(BaseModel):
    event_id: int
    section: str
    total_tickets: int
    available_tickets: int
    reserved_tickets: int
    sold_tickets: int
    subsections: List[SubsectionAvailability]

    class Config:
        json_schema_extra = {
            'example': {
                'event_id': 1,
                'section': 'A',
                'total_tickets': 500,
                'available_tickets': 496,
                'reserved_tickets': 3,
                'sold_tickets': 1,
                'subsections': [
                    {
                        'subsection': 1,
                        'total_tickets': 100,
                        'available_tickets': 99,
                        'reserved_tickets': 1,
                        'sold_tickets': 0,
                    }
                ],
            }
        }


class SubsectionStatus(BaseModel):
    subsection: int
    total_seats: int
    available_seats: int
    status: str


class PriceGroup(BaseModel):
    price: int
    subsections: List[SubsectionStatus]


class EventStatusResponse(BaseModel):
    event_id: int
    price_groups: List[PriceGroup]

    class Config:
        json_schema_extra = {
            'example': {
                'event_id': 1,
                'price_groups': [
                    {
                        'price': 8800,
                        'subsections': [
                            {
                                'subsection': 1,
                                'total_seats': 100,
                                'available_seats': 100,
                                'status': 'Available',
                            },
                            {
                                'subsection': 2,
                                'total_seats': 100,
                                'available_seats': 64,
                                'status': '64 seat(s) remaining',
                            },
                        ],
                    }
                ],
            }
        }
