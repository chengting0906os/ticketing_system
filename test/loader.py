"""
Test Loader Module

Consolidates all BDD steps and service fixtures for pytest.
This module is imported by conftest.py to register all components.

Organization:
- Service Fixtures
- BDD Steps (Given/When/Then)
"""

# =============================================================================
# Service Fixtures
# =============================================================================
from test.service.ticketing.fixtures import *  # noqa: F401, F403

# =============================================================================
# Ticketing Service Steps (via conftest.py in each test directory)
# =============================================================================
# Note: BDD steps are defined in their respective conftest.py files
# and are auto-discovered by pytest:
# - test/service/ticketing/booking/conftest.py
# - test/service/ticketing/event_ticketing/conftest.py

# =============================================================================
# Common Reusable Steps (Given/When/Then steps for API calls)
# =============================================================================
from test.bdd_conftest.given_step_conftest import *  # noqa: F401, F403
from test.bdd_conftest.then_step_conftest import *  # noqa: F401, F403
from test.bdd_conftest.when_step_conftest import *  # noqa: F401, F403
from test.bdd_conftest.sse_step_conftest import *  # noqa: F401, F403
