"""Fixtures for pytest_bdd_ng tests."""

import pytest


@pytest.fixture
def calculator_state():
    """State holder for calculator tests."""
    return {'numbers': [], 'result': None}
