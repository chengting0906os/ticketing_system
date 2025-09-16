import pytest


@pytest.fixture
def context():
    return {}


@pytest.fixture
def reservation_state():
    class ReservationState:
        pass

    return ReservationState()
