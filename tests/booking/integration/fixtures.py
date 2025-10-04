import pytest


@pytest.fixture
def booking_state():
    return {}


@pytest.fixture(autouse=True)
def mock_kafka_for_booking_tests(monkeypatch):
    """Auto-mock Kafka infrastructure for all booking tests"""

    # Mock publish_domain_event to prevent Kafka calls
    async def mock_publish(*args, **kwargs):
        pass

    monkeypatch.setattr(
        'src.booking.app.command.create_booking_use_case.publish_domain_event', mock_publish
    )
    monkeypatch.setattr(
        'src.booking.app.command.mock_payment_and_update_status_to_completed_use_case.publish_domain_event',
        mock_publish,
    )
