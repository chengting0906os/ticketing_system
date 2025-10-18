"""Shared Kernel Interfaces"""

from src.service.shared_kernel.app.interface.i_seat_state_command_handler import (
    ISeatStateCommandHandler,
)
from src.service.shared_kernel.app.interface.i_seat_state_query_handler import (
    ISeatStateQueryHandler,
)

__all__ = [
    'ISeatStateCommandHandler',
    'ISeatStateQueryHandler',
]
