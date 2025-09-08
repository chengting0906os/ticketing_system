import pytest


@pytest.fixture
def user_state():
    return {'request_data': {}, 'response': None}
