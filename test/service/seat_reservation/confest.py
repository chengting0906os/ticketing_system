"""Pytest configuration for seat reservation integration test"""

# Import shared fixtures and steps
from test.service.seat_reservation.fixtures import context, http_server
from test.service.ticketing.integration.steps.event_ticketing.given import event_exists


# Re-export fixtures for use in test
# Note: 'client' and user steps are defined in test/conftest.py (global fixtures)
__all__ = [
    'context',
    'event_exists',
    'http_server',
]
