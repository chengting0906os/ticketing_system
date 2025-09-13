# Event test constants to eliminate duplication across test files

# Default venue configurations
DEFAULT_VENUE_NAME = 'Default Venue'
TAIPEI_ARENA = 'Taipei Arena'
TAIPEI_DOME = 'Taipei Dome'

# Default seating configurations (as dicts for API usage)
DEFAULT_SEATING_CONFIG = {
    'sections': [{'name': 'A', 'subsections': [{'number': 1, 'rows': 25, 'seats_per_row': 20}]}]
}

ALTERNATIVE_SEATING_CONFIG = {
    'sections': [{'name': 'B', 'subsections': [{'number': 2, 'rows': 30, 'seats_per_row': 25}]}]
}

# JSON string versions for database insertion and feature files
DEFAULT_SEATING_CONFIG_JSON = (
    '{"sections": [{"name": "A", "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]}'
)
ALTERNATIVE_SEATING_CONFIG_JSON = (
    '{"sections": [{"name": "B", "subsections": [{"number": 2, "rows": 30, "seats_per_row": 25}]}]}'
)

# Additional seating configs for variety in tests
SEATING_CONFIGS = [
    '{"sections": [{"name": "A", "subsections": [{"number": 1, "rows": 25, "seats_per_row": 20}]}]}',
    '{"sections": [{"name": "B", "subsections": [{"number": 2, "rows": 30, "seats_per_row": 25}]}]}',
    '{"sections": [{"name": "C", "subsections": [{"number": 3, "rows": 25, "seats_per_row": 20}]}]}',
    '{"sections": [{"name": "D", "subsections": [{"number": 4, "rows": 30, "seats_per_row": 25}]}]}',
    '{"sections": [{"name": "E", "subsections": [{"number": 5, "rows": 25, "seats_per_row": 20}]}]}',
    '{"sections": [{"name": "F", "subsections": [{"number": 6, "rows": 30, "seats_per_row": 25}]}]}',
]

VENUE_NAMES = [TAIPEI_ARENA, TAIPEI_DOME]
