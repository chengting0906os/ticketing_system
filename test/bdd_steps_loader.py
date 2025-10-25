"""
BDD Steps Import Module

Consolidates all Gherkin step definitions (Given/When/Then) from various services.
This module is imported by conftest.py to register all BDD steps with pytest-bdd.

Organization:
- BDD Example steps
- Seat Reservation Service steps
- Ticketing Service steps
- Shared utility steps
"""

# =============================================================================
# BDD Example Steps
# =============================================================================
from test.pytest_bdd_ng_example.fixtures import *  # noqa: E402, F403
from test.pytest_bdd_ng_example.given import *  # noqa: E402, F403
from test.pytest_bdd_ng_example.then import *  # noqa: E402, F403
from test.pytest_bdd_ng_example.when import *  # noqa: E402, F403

# =============================================================================
# Seat Reservation Steps (now part of Ticketing Service)
# =============================================================================
from test.service.ticketing.integration.steps.seat_reservation.given import *  # noqa: E402, F403
from test.service.ticketing.integration.steps.seat_reservation.then import *  # noqa: E402, F403
from test.service.ticketing.integration.steps.seat_reservation.when import *  # noqa: E402, F403

# =============================================================================
# Ticketing Service Steps
# =============================================================================
from test.service.ticketing.integration.steps.booking.given import *  # noqa: E402, F403
from test.service.ticketing.integration.steps.booking.then import *  # noqa: E402, F403
from test.service.ticketing.integration.steps.booking.when import *  # noqa: E402, F403
from test.service.ticketing.integration.steps.event_ticketing.given import *  # noqa: E402, F403
from test.service.ticketing.integration.steps.event_ticketing.then import *  # noqa: E402, F403
from test.service.ticketing.integration.steps.event_ticketing.when import *  # noqa: E402, F403
from test.service.ticketing.integration.steps.user.given import *  # noqa: E402, F403
from test.service.ticketing.integration.steps.user.then import *  # noqa: E402, F403
from test.service.ticketing.integration.steps.user.when import *  # noqa: E402, F403

# =============================================================================
# Shared Steps
# =============================================================================
from test.shared.given import *  # noqa: E402, F403
from test.shared.then import *  # noqa: E402, F403
