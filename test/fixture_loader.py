"""
Service Fixtures Import Module

Consolidates all service-specific test fixtures.
This module is imported by conftest.py to make service fixtures available to all tests.

Organization:
- Ticketing Service fixtures (includes Seat Reservation fixtures)
"""

# =============================================================================
# Service-Specific Fixtures
# =============================================================================
from test.service.ticketing.fixtures import *  # noqa: E402, F403
