"""User Given step definitions."""

from pytest_bdd import given
from tests.steps.user.shared import UserState


@given('I have a database connection')
def setup_database():
    """Set up database connection for testing."""
    UserState.reset()
    UserState.setup_db()
