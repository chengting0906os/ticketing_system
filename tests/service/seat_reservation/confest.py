"""Pytest configuration for seat reservation integration tests"""

# Import shared fixtures and steps
from tests.service.seat_reservation.fixtures import context, http_server
from tests.service.ticketing.integration.steps.event_ticketing.given import event_exists

# Re-export fixtures for use in tests
# Note: 'client' and user steps are defined in tests/conftest.py (global fixtures)
__all__ = [
    'context',
    'event_exists',
    'http_server',
]
