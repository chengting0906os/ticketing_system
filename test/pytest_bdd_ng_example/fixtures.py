import pytest


@pytest.fixture
def calculator_state():
    return {'numbers': [], 'result': None}
