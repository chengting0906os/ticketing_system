"""
Reservation Service - Application Interfaces

Defines abstractions for the reservation service's application layer.
"""

from src.service.reservation.app.interface.i_seat_state_command_handler import (
    ISeatStateCommandHandler,
)
from src.service.reservation.app.interface.i_seat_state_query_handler import (
    ISeatStateQueryHandler,
)

__all__ = [
    'ISeatStateCommandHandler',
    'ISeatStateQueryHandler',
]
