"""Selection Mode Enum"""

from enum import StrEnum


class SelectionMode(StrEnum):
    """Seat selection mode for booking"""

    MANUAL = 'manual'
    BEST_AVAILABLE = 'best_available'
