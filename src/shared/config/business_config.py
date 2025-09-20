"""Business logic configuration and constants."""

from typing import Final


class BookingLimits:
    """Booking-related business limits."""

    MAX_TICKETS_PER_BOOKING: Final[int] = 4
    MIN_TICKETS_PER_BOOKING: Final[int] = 1


class SeatIdentifierFormat:
    """Constants for seat identifier format."""

    SEPARATOR: Final[str] = '-'
    EXPECTED_PARTS: Final[int] = 4
    FORMAT_DESCRIPTION: Final[str] = 'section-subsection-row-seat'
    EXAMPLE: Final[str] = 'A-1-1-1'


class SelectionModes:
    """Seat selection mode constants."""

    MANUAL: Final[str] = 'manual'
    BEST_AVAILABLE: Final[str] = 'best_available'


class TicketStatus:
    """Ticket status constants."""

    AVAILABLE: Final[str] = 'available'
    RESERVED: Final[str] = 'reserved'
    SOLD: Final[str] = 'sold'
