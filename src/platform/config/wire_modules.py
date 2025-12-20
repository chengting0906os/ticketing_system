"""
Wire Modules Configuration

Defines the modules that need dependency injection wiring.
Shared between production and test environments.
"""

from types import ModuleType

from src.service.ticketing.app.command import (
    create_booking_use_case,
    create_event_and_tickets_use_case,
    mock_payment_and_update_booking_status_to_completed_and_ticket_to_paid_use_case,
    update_booking_status_to_cancelled_use_case,
)
from src.service.ticketing.app.query import (
    get_booking_use_case,
    list_bookings_use_case,
    list_events_use_case,
)
from src.service.ticketing.driving_adapter.http_controller import user_controller


WIRE_MODULES: list[ModuleType] = [
    create_booking_use_case,
    update_booking_status_to_cancelled_use_case,
    mock_payment_and_update_booking_status_to_completed_and_ticket_to_paid_use_case,
    list_bookings_use_case,
    get_booking_use_case,
    create_event_and_tickets_use_case,
    list_events_use_case,
    user_controller,
]
