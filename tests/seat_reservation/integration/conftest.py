"""Pytest configuration for seat reservation integration tests"""

# Import shared fixtures and steps
from tests.event_ticketing.integration.fixtures import mock_kafka_infrastructure
from tests.event_ticketing.integration.steps.given import event_exists
from tests.seat_reservation.integration.fixtures import context, http_server


# Re-export fixtures for use in tests
# Note: 'client' and user steps are defined in tests/conftest.py (global fixtures)
__all__ = [
    'context',
    'event_exists',
    'mock_kafka_infrastructure',
    'http_server',
]
