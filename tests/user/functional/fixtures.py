"""Fixtures for user BDD tests."""

import pytest


@pytest.fixture
def user_state():
    """Provide user state for tests."""
    return {'request_data': {}, 'response': None}
