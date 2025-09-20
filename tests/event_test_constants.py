# Event test constants to eliminate duplication across test files

# Default venue configurations
DEFAULT_VENUE_NAME = 'Default Venue'
TAIPEI_ARENA = 'Taipei Arena'
TAIPEI_DOME = 'Taipei Dome'

# Default seating configurations (as dicts for API usage)
DEFAULT_SEATING_CONFIG = {
    'sections': [
        {
            'name': 'A',
            'price': 1000,
            'subsections': [{'number': 1, 'rows': 25, 'seats_per_row': 20}],
        }
    ]
}

ALTERNATIVE_SEATING_CONFIG = {
    'sections': [
        {
            'name': 'B',
            'price': 1200,
            'subsections': [{'number': 2, 'rows': 30, 'seats_per_row': 25}],
        }
    ]
}

# JSON string versions for database insertion and feature files
DEFAULT_SEATING_CONFIG_JSON = '{"sections": [{"name": "A", "price": 1000, "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]}'

# Availability test seating configuration (A-E sections with 2 subsections each)
AVAILABILITY_SEATING_CONFIG_JSON = '{"sections": [{"name": "A", "price": 1000, "subsections": [{"number": 1, "rows": 10, "seats_per_row": 25}, {"number": 2, "rows": 10, "seats_per_row": 25}]}, {"name": "B", "price": 1000, "subsections": [{"number": 1, "rows": 10, "seats_per_row": 25}, {"number": 2, "rows": 10, "seats_per_row": 25}]}, {"name": "C", "price": 1000, "subsections": [{"number": 1, "rows": 10, "seats_per_row": 25}, {"number": 2, "rows": 10, "seats_per_row": 25}]}, {"name": "D", "price": 1000, "subsections": [{"number": 1, "rows": 10, "seats_per_row": 25}, {"number": 2, "rows": 10, "seats_per_row": 25}]}, {"name": "E", "price": 1000, "subsections": [{"number": 1, "rows": 10, "seats_per_row": 25}, {"number": 2, "rows": 10, "seats_per_row": 25}]}]}'

# Section-specific seating configuration for testing individual sections (A section with 5 subsections)
SECTION_SEATING_CONFIG_JSON = '{"sections": [{"name": "A", "price": 1000, "subsections": [{"number": 1, "rows": 10, "seats_per_row": 10}, {"number": 2, "rows": 10, "seats_per_row": 10}, {"number": 3, "rows": 10, "seats_per_row": 10}, {"number": 4, "rows": 10, "seats_per_row": 10}, {"number": 5, "rows": 10, "seats_per_row": 10}]}]}'
ALTERNATIVE_SEATING_CONFIG_JSON = '{"sections": [{"name": "B", "price": 1200, "subsections": [{"number": 2, "rows": 30, "seats_per_row": 25}]}]}'

# Additional seating configs for variety in tests
SEATING_CONFIGS = [
    '{"sections": [{"name": "A", "price": 1000, "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]}',
    '{"sections": [{"name": "B", "price": 1200, "subsections": [{"number": 2, "rows": 30, "seats_per_row": 25}]}]}',
    '{"sections": [{"name": "C", "price": 800, "subsections": [{"number": 3, "rows": 25, "seats_per_row": 20}]}]}',
    '{"sections": [{"name": "D", "price": 1500, "subsections": [{"number": 4, "rows": 30, "seats_per_row": 25}]}]}',
    '{"sections": [{"name": "E", "price": 900, "subsections": [{"number": 5, "rows": 25, "seats_per_row": 20}]}]}',
    '{"sections": [{"name": "F", "price": 1100, "subsections": [{"number": 6, "rows": 30, "seats_per_row": 25}]}]}',
]

VENUE_NAMES = [TAIPEI_ARENA, TAIPEI_DOME]
