"""
Service Fixtures Import Module

Consolidates all service-specific test fixtures.
This module is imported by conftest.py to make service fixtures available to all tests.

Organization:
- Seat Reservation Service fixtures
- Ticketing Service fixtures
"""

# =============================================================================
# Service-Specific Fixtures
# =============================================================================
from test.service.reservation.fixtures import *  # noqa: E402, F403
from test.service.ticketing.fixtures import *  # noqa: E402, F403
