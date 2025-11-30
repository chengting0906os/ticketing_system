# Event test constants to eliminate duplication across test files

# Default venue configurations
DEFAULT_VENUE_NAME = 'Default Venue'
TAIPEI_ARENA = 'Taipei Arena'
TAIPEI_DOME = 'Taipei Dome'

# Default seating configurations (compact format)
# rows/cols at top level, subsections as integer count
DEFAULT_SEATING_CONFIG = {
    'rows': 25,
    'cols': 20,
    'sections': [
        {
            'name': 'A',
            'price': 1000,
            'subsections': 1,
        }
    ],
}

ALTERNATIVE_SEATING_CONFIG = {
    'rows': 30,
    'cols': 25,
    'sections': [
        {
            'name': 'B',
            'price': 1200,
            'subsections': 1,
        }
    ],
}

# JSON string versions for database insertion and feature files
DEFAULT_SEATING_CONFIG_JSON = (
    '{"rows": 25, "cols": 20, "sections": [{"name": "A", "price": 1000, "subsections": 1}]}'
)

# Availability test seating configuration (A-E sections with 2 subsections each)
AVAILABILITY_SEATING_CONFIG_JSON = '{"rows": 10, "cols": 25, "sections": [{"name": "A", "price": 1000, "subsections": 2}, {"name": "B", "price": 1000, "subsections": 2}, {"name": "C", "price": 1000, "subsections": 2}, {"name": "D", "price": 1000, "subsections": 2}, {"name": "E", "price": 1000, "subsections": 2}]}'

# Section-specific seating configuration for testing individual sections (A section with 5 subsections)
SECTION_SEATING_CONFIG_JSON = (
    '{"rows": 10, "cols": 10, "sections": [{"name": "A", "price": 1000, "subsections": 5}]}'
)
ALTERNATIVE_SEATING_CONFIG_JSON = (
    '{"rows": 30, "cols": 25, "sections": [{"name": "B", "price": 1200, "subsections": 1}]}'
)

# Additional seating configs for variety in test
SEATING_CONFIGS = [
    '{"rows": 25, "cols": 20, "sections": [{"name": "A", "price": 1000, "subsections": 1}]}',
    '{"rows": 30, "cols": 25, "sections": [{"name": "B", "price": 1200, "subsections": 1}]}',
    '{"rows": 25, "cols": 20, "sections": [{"name": "C", "price": 800, "subsections": 1}]}',
    '{"rows": 30, "cols": 25, "sections": [{"name": "D", "price": 1500, "subsections": 1}]}',
    '{"rows": 25, "cols": 20, "sections": [{"name": "E", "price": 900, "subsections": 1}]}',
    '{"rows": 30, "cols": 25, "sections": [{"name": "F", "price": 1100, "subsections": 1}]}',
]

VENUE_NAMES = [TAIPEI_ARENA, TAIPEI_DOME]
